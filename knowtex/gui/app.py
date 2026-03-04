"""Main KnowTeX GUI application.

Supports two modes:
- Manual mode: reads explicit \\uses{}/\\proves{} annotations
- Infer mode: infers dependencies from \\ref/\\Cref/\\eqref and heuristics
"""

import logging
import os
import re
import tempfile
from collections import defaultdict

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from knowtex.core.constants import (
    ZOOM_STEP_IN, ZOOM_STEP_OUT, PREVIEW_DPI, EXPORT_DPI,
    SNIPPET_MAX_DISPLAY_LEN,
)
from knowtex.core.data import DependencyEdge
from knowtex.core.file_expand import load_and_expand
from knowtex.core.structure import (
    detect_doc_class, find_chapter_ranges, find_section_ranges,
    assign_sections,
)
from knowtex.core.parser import parse_latex_structure
from knowtex.core.graph import build_graph
from knowtex.core.cycles import find_cycles
from knowtex.deps.manual import extract_manual_edges
from knowtex.deps.infer import run_inference
from knowtex.deps.index_registry import build_index_registry
from knowtex.gui.dialogs import EnvConfigDialog, _center_dialog
from knowtex.gui.preview import PreviewMixin, parse_cmapx

try:
    from pygraphviz import AGraph
    from dot2tex import dot2tex
    from PIL import Image, ImageTk
except Exception as e:
    AGraph = None
    dot2tex = None
    Image = None
    ImageTk = None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None

logger = logging.getLogger("knowtex")


class KnowTex(tk.Tk, PreviewMixin):
    """Unified main application window for KnowTeX (manual + infer modes)."""

    def __init__(self):
        super().__init__()
        self.title("KnowTeX: Knowledge Dependency from TeX")
        try:
            self.state("zoomed")
        except tk.TclError:
            self.attributes("-zoomed", True)

        if _IMPORT_ERROR:
            messagebox.showerror(
                "Import error",
                "One or more required packages failed to import:\n\n"
                f"{_IMPORT_ERROR}\n\n"
                "Please install: pygraphviz, dot2tex, pylatexenc, Pillow\n"
                "and ensure Graphviz is installed and on PATH."
            )

        self._tex_path = tk.StringVar()
        self._mode = tk.StringVar(value="infer")
        self._doc_class = "article"
        self._expanded_tex = None
        self._filtered_tex = None
        self._nodes = []
        self._node_by_index = {}
        self._label_to_node = {}
        self._proofs = []
        self._edges = []
        self._cycle_edges = set()
        self._section_assignments = {}
        self._section_ranges = []
        self._all_sections = []
        self._discovered_envs = set()
        self._env_config = {}
        self._excluded_envs = set()
        self._index_registry = None
        self._label_to_info = {}
        self._edges_mode = None

        self._view_mode = tk.StringVar(value="macro")
        self._micro_section = tk.StringVar()
        self._skip_tred = tk.BooleanVar(value=False)

        self._init_preview_state()
        self._mode.trace_add("write", self._on_mode_change)

        self._build_gui()

    def _on_mode_change(self, *_args):
        """Reset edges and config when the user switches mode."""
        if not self._nodes:
            return
        self._edges = []
        self._cycle_edges = set()
        self._env_config = {}
        self._excluded_envs = set()
        self._index_registry = None
        self._edges_mode = None
        self._base_pil = None
        self._map_areas = []
        self._img_item = None
        self._canvas.delete("all")
        self._set_status(
            "Mode changed. Please re-configure environments."
        )

    def _build_gui(self):
        # ---- Mode + File selection ----
        top = ttk.LabelFrame(self, text="Load LaTeX File", padding=8)
        top.pack(fill="x", padx=8, pady=(8, 4))

        mode_frame = ttk.Frame(top)
        mode_frame.pack(side="left")
        ttk.Label(mode_frame, text="Mode:").pack(side="left")
        ttk.Radiobutton(
            mode_frame, text="Manual (\\uses{})",
            variable=self._mode, value="manual",
        ).pack(side="left", padx=4)
        ttk.Radiobutton(
            mode_frame, text="Infer (\\ref-based)",
            variable=self._mode, value="infer",
        ).pack(side="left", padx=4)

        ttk.Label(top, text="  Main .tex file:").pack(side="left")
        ttk.Entry(top, textvariable=self._tex_path, width=55).pack(
            side="left", padx=6)
        ttk.Button(top, text="Browse...", command=self._browse_tex).pack(
            side="left")
        ttk.Button(top, text="Load & Scan", command=self._load_and_scan).pack(
            side="left", padx=12)

        # ---- View mode controls ----
        view_frame = ttk.Frame(self, padding=(8, 4))
        view_frame.pack(fill="x")
        ttk.Label(view_frame, text="View:").pack(side="left")
        ttk.Radiobutton(
            view_frame, text="Macro (all)",
            variable=self._view_mode, value="macro",
        ).pack(side="left", padx=6)
        ttk.Radiobutton(
            view_frame, text="Micro (single section)",
            variable=self._view_mode, value="micro",
        ).pack(side="left")
        self._micro_combo = ttk.Combobox(
            view_frame, textvariable=self._micro_section,
            state="readonly", width=40,
        )
        self._micro_combo.pack(side="left", padx=6)

        ttk.Checkbutton(
            view_frame, text="Skip transitive reduction",
            variable=self._skip_tred,
        ).pack(side="right", padx=12)

        # ---- Action buttons ----
        btns = ttk.Frame(self, padding=8)
        btns.pack(fill="x")
        ttk.Button(
            btns, text="Configure Environments...",
            command=self._show_env_config,
        ).pack(side="left")
        ttk.Button(
            btns, text="Review Edges",
            command=self._show_review,
        ).pack(side="left", padx=8)
        ttk.Button(
            btns, text="Preview Graph",
            command=self._preview,
        ).pack(side="left", padx=8)
        ttk.Button(btns, text="Export", command=self._export).pack(side="left")

        # ---- Status bar ----
        self._status = tk.StringVar(value="Ready. Load a LaTeX file to begin.")
        ttk.Label(
            self, textvariable=self._status, relief="sunken", anchor="w",
        ).pack(fill="x", side="bottom")

        # ---- Main content area ----
        pw = ttk.Panedwindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=8, pady=4)

        # Left: canvas
        canvas_frame = ttk.Frame(pw)
        pw.add(canvas_frame, weight=4)

        toolbar = ttk.Frame(canvas_frame)
        toolbar.pack(fill="x", side="top")
        ttk.Button(
            toolbar, text="Zoom -",
            command=lambda: self._zoom_by(ZOOM_STEP_OUT),
        ).pack(side="left")
        ttk.Button(
            toolbar, text="Zoom +",
            command=lambda: self._zoom_by(ZOOM_STEP_IN),
        ).pack(side="left")
        ttk.Button(toolbar, text="Fit", command=self._zoom_fit).pack(
            side="left", padx=(8, 0))
        ttk.Button(toolbar, text="100%", command=self._zoom_reset).pack(
            side="left")

        self._canvas = tk.Canvas(canvas_frame, bg="#fafafa")
        xscroll = ttk.Scrollbar(
            canvas_frame, orient="horizontal",
            command=self._canvas.xview,
        )
        yscroll = ttk.Scrollbar(
            canvas_frame, orient="vertical",
            command=self._canvas.yview,
        )
        self._canvas.configure(
            xscrollcommand=xscroll.set, yscrollcommand=yscroll.set,
        )
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self._canvas.pack(fill="both", expand=True, side="left")

        # Right: info panel
        info_frame = ttk.Frame(pw, padding=8)
        pw.add(info_frame, weight=1)

        ttk.Label(info_frame, text="Selection").pack(anchor="w")
        self._info_title = tk.StringVar(value="Click a node")
        ttk.Label(
            info_frame, textvariable=self._info_title, wraplength=260,
        ).pack(anchor="w", pady=(2, 8))

        self._info_text = tk.Text(info_frame, height=30, wrap="word")
        self._info_text.pack(fill="both", expand=True)
        self._info_text.insert("1.0", "No node selected.\n")
        self._info_text.configure(state="disabled")

        # Canvas bindings
        self._bind_canvas_events()

    # ---- Browse ----
    def _browse_tex(self):
        path = filedialog.askopenfilename(
            title="Select main .tex file",
            filetypes=[("TeX files", "*.tex"), ("All files", "*.*")],
        )
        if path:
            self._tex_path.set(path)

    # ---- Range selection dialog ----
    def _choose_ranges_dialog(self, ranges, range_type):
        """Show dialog for user to pick which chapters/sections to scan.

        Returns list of (start, end) tuples, empty list if none selected,
        or None if cancelled.
        """
        if not ranges:
            return None

        win = tk.Toplevel(self)
        win.title(f"Select {range_type}s to scan")
        win.transient(self)
        win.grab_set()
        win.minsize(640, 500)

        ttk.Label(win, text=f"Choose the {range_type}s to include:").pack(
            anchor="w", padx=10, pady=(10, 6))

        outer = ttk.Frame(win)
        outer.pack(fill="both", expand=True, padx=10, pady=6)
        canvas = tk.Canvas(outer, borderwidth=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        vars_ = []
        for i, rng in enumerate(ranges, 1):
            v = tk.BooleanVar(value=True)
            text = f"{i}. {rng['title']}"
            ttk.Checkbutton(inner, text=text, variable=v).pack(
                anchor="w", pady=2)
            vars_.append(v)

        selected_ranges = []
        cancelled = False

        def on_ok():
            for v, rng in zip(vars_, ranges):
                if v.get():
                    selected_ranges.append((rng["start"], rng["end"]))
            win.destroy()

        def on_all():
            for v in vars_:
                v.set(True)

        def on_none():
            for v in vars_:
                v.set(False)

        def on_cancel():
            nonlocal cancelled
            cancelled = True
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="All", command=on_all).pack(side="left")
        ttk.Button(btns, text="None", command=on_none).pack(
            side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right", padx=4)

        win.update_idletasks()
        req_w = max(640, win.winfo_reqwidth() + 40)
        req_h = max(500, win.winfo_reqheight() + 40)
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        req_w = min(req_w, sw)
        req_h = min(req_h, sh)
        win.geometry(f"{req_w}x{req_h}")
        _center_dialog(win, self)
        self.wait_window(win)

        if cancelled:
            return None
        return selected_ranges

    # ---- Load & Scan ----
    def _load_and_scan(self):
        texfile = self._tex_path.get().strip()
        if not texfile:
            messagebox.showwarning("Missing file",
                                   "Please choose a .tex file first.")
            return

        self._set_status("Loading and expanding project...")
        self.update_idletasks()

        try:
            self._expanded_tex = load_and_expand(texfile)
            self._doc_class = detect_doc_class(self._expanded_tex)

            if self._doc_class == "book":
                all_ranges = find_chapter_ranges(self._expanded_tex)
                range_type = "chapter"
            else:
                all_ranges = find_section_ranges(self._expanded_tex)
                range_type = "section"

            self._set_status(
                f"Document class: {self._doc_class}. "
                f"Found {len(all_ranges)} {range_type}(s)."
            )
            self.update_idletasks()

            if all_ranges:
                selected = self._choose_ranges_dialog(all_ranges, range_type)
                if selected is None:
                    self._set_status("Scan cancelled.")
                    return
                if not selected:
                    self._set_status(
                        f"No {range_type}s selected; nothing to scan.")
                    return

                parts = []
                for s, e in selected:
                    parts.append(self._expanded_tex[s:e])
                self._filtered_tex = (
                    "\n\n% [knowtex range separator]\n\n"
                ).join(parts)

                self._set_status(
                    f"Scanning {len(selected)} of {len(all_ranges)}"
                    f" {range_type}(s)..."
                )
            else:
                self._filtered_tex = self._expanded_tex
                self._set_status(
                    "No chapters/sections found; scanning whole document..."
                )

            self.update_idletasks()

            (self._nodes,
             self._node_by_index,
             self._label_to_node,
             self._proofs,
             self._discovered_envs) = parse_latex_structure(
                self._filtered_tex
            )

            # Recalculate section ranges on the filtered text
            if self._doc_class == "book":
                self._section_ranges = find_chapter_ranges(
                    self._filtered_tex)
            else:
                self._section_ranges = find_section_ranges(
                    self._filtered_tex)

            self._section_assignments = assign_sections(
                self._nodes, self._section_ranges)
            self._all_sections = []
            seen = set()
            for ni in self._nodes:
                sec = self._section_assignments.get(
                    ni.label, "(ungrouped)")
                if sec not in seen:
                    self._all_sections.append(sec)
                    seen.add(sec)

            self._label_to_info = {ni.label: ni for ni in self._nodes}

            self._micro_combo["values"] = self._all_sections
            if self._all_sections:
                self._micro_section.set(self._all_sections[0])

            # Clear previous state
            self._env_config = {}
            self._excluded_envs = set()
            self._index_registry = None
            self._edges = []
            self._cycle_edges = set()

            # Summary
            env_counts = defaultdict(int)
            for n in self._nodes:
                env_counts[n.env] += 1
            summary_parts = [
                f"{env}: {cnt}"
                for env, cnt in sorted(env_counts.items())
            ]
            self._set_status(
                f"Scanned {len(self._nodes)} nodes across "
                f"{len(self._discovered_envs)} environment type(s). "
                f"{', '.join(summary_parts)}. Now configure environments."
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._set_status("Error during scan.")

    # ---- Environment Configuration ----
    def _show_env_config(self):
        if not self._discovered_envs:
            messagebox.showwarning("No data", "Load and scan a file first.")
            return

        mode = self._mode.get()
        show_is_defn = (mode == "infer")

        dlg = EnvConfigDialog(
            self, self._discovered_envs, show_is_defn=show_is_defn)
        self.wait_window(dlg)

        if dlg.result is None:
            self._set_status("Environment configuration cancelled.")
            return

        full_config = dlg.result
        self._env_config = {}
        self._excluded_envs = set()
        for env_name, cfg in full_config.items():
            if cfg.get("include", True):
                self._env_config[env_name] = {
                    "shape": cfg["shape"],
                    "border": cfg["border"],
                    "fill": cfg["fill"],
                }
                if show_is_defn:
                    self._env_config[env_name]["is_defn"] = cfg.get(
                        "is_defn", False)
            else:
                self._excluded_envs.add(env_name)

        # Filter nodes to included environments only
        included_nodes = [
            n for n in self._nodes if n.env not in self._excluded_envs
        ]
        included_node_by_index = {n.index: n for n in included_nodes}
        included_label_to_node = {
            n.label: n
            for n in included_nodes if n.label in self._label_to_node
        }

        if mode == "manual":
            # Manual mode: extract \\uses{}/\\proves{}
            self._edges = extract_manual_edges(
                included_nodes, included_node_by_index,
                included_label_to_node, self._proofs,
            )
        else:
            # Infer mode
            definition_envs = {
                env_name
                for env_name, cfg in self._env_config.items()
                if cfg.get("is_defn", False)
            }

            self._index_registry = None
            scan_tex = self._filtered_tex or self._expanded_tex
            if scan_tex:
                self._index_registry = build_index_registry(
                    included_nodes, self._proofs, scan_tex
                )

            self._edges = run_inference(
                included_nodes, included_node_by_index,
                included_label_to_node, self._proofs,
                index_registry=self._index_registry,
                definition_envs=definition_envs,
            )

        # Remove edges referencing excluded nodes
        excluded_labels = {
            n.label
            for n in self._nodes if n.env in self._excluded_envs
        }
        self._edges = [
            e for e in self._edges
            if e.source not in excluded_labels
            and e.target not in excluded_labels
        ]

        # Record which mode produced these edges
        self._edges_mode = mode

        # Detect cycles
        self._cycle_edges = find_cycles(self._edges)

        det_count = sum(
            1 for e in self._edges if e.edge_type == "deterministic"
        )
        heu_count = sum(
            1 for e in self._edges if e.edge_type == "heuristic"
        )
        man_count = sum(
            1 for e in self._edges if e.edge_type == "manual"
        )
        cycle_msg = ""
        if self._cycle_edges:
            cycle_msg = (
                f" WARNING: {len(self._cycle_edges)} edge(s) form cycles!"
            )

        incl_count = len(self._env_config)
        excl_count = len(self._excluded_envs)
        excl_msg = f" ({excl_count} excluded)" if excl_count else ""

        if mode == "manual":
            self._set_status(
                f"Configured {incl_count} environment(s){excl_msg}. "
                f"Found {len(self._edges)} manual edges "
                f"({man_count} from \\uses{{}})."
                + cycle_msg
            )
        else:
            self._set_status(
                f"Configured {incl_count} environment(s){excl_msg}. "
                f"Inferred {len(self._edges)} edges "
                f"({det_count} deterministic, {heu_count} heuristic)."
                + cycle_msg
            )

        if self._cycle_edges:
            messagebox.showwarning(
                "Cycles Detected",
                f"{len(self._cycle_edges)} edge(s) form cycles.\n\n"
                "These edges will be highlighted in red in the Review table.\n"
                "Transitive reduction will be applied only to non-cycle edges.\n"
                "You can delete cycle edges in Review to break cycles, "
                "or leave them as-is."
            )

    # ---- Review ----
    def _show_review(self):
        if not self._nodes:
            messagebox.showwarning("No data", "Load and scan a file first.")
            return
        if not self._env_config:
            messagebox.showwarning("Not configured",
                                   "Configure environments first.")
            return

        win = tk.Toplevel(self)
        win.title("Review Dependencies")
        win.transient(self)
        win.minsize(900, 550)

        toolbar = ttk.Frame(win, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(
            toolbar, text="Add Edge...",
            command=lambda: self._add_edge_dialog(win, tree),
        ).pack(side="left")
        ttk.Button(
            toolbar, text="Delete Selected",
            command=lambda: self._delete_selected_edge(tree),
        ).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Close", command=win.destroy).pack(
            side="right")

        if self._cycle_edges:
            ttk.Label(
                toolbar,
                text=f"  Cycle edges ({len(self._cycle_edges)}) shown in red",
                foreground="red",
            ).pack(side="left", padx=16)

        cols = ("source", "target", "type", "location", "rule")
        style = ttk.Style()
        style.configure("Treeview", rowheight=30)
        tree = ttk.Treeview(
            win, columns=cols, show="headings", selectmode="extended")
        tree.heading("source", text="Source")
        tree.heading("target", text="Target")
        tree.heading("type", text="Type")
        tree.heading("location", text="Location")
        tree.heading("rule", text="Rule")
        tree.column("source", width=220)
        tree.column("target", width=220)
        tree.column("type", width=120)
        tree.column("location", width=120)
        tree.column("rule", width=60)

        tree.tag_configure("cycle", foreground="red")

        scrollbar = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(fill="both", expand=True, padx=8, side="left")
        scrollbar.pack(fill="y", side="right", padx=(0, 8))

        self._populate_review_tree(tree)

        win.update_idletasks()
        _center_dialog(win, self)

    def _populate_review_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)
        for i, e in enumerate(self._edges):
            tags = ()
            if e.key() in self._cycle_edges:
                tags = ("cycle",)
            tree.insert("", "end", iid=str(i), values=(
                e.source, e.target, e.edge_type, e.location, e.rule,
            ), tags=tags)

    def _delete_selected_edge(self, tree):
        selected = tree.selection()
        if not selected:
            return
        indices = sorted([int(s) for s in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self._edges):
                del self._edges[idx]
        self._cycle_edges = find_cycles(self._edges)
        self._populate_review_tree(tree)
        self._set_status(
            f"Deleted {len(indices)} edge(s). "
            f"{len(self._edges)} remaining."
        )

    def _add_edge_dialog(self, parent, tree):
        dlg = tk.Toplevel(parent)
        dlg.title("Add Edge")
        dlg.transient(parent)
        dlg.grab_set()
        dlg.minsize(500, 250)

        all_labels = sorted(self._label_to_node.keys())

        ttk.Label(dlg, text="Source:").grid(
            row=0, column=0, padx=8, pady=8, sticky="w")
        src_var = tk.StringVar()
        ttk.Combobox(dlg, textvariable=src_var, values=all_labels,
                     width=30).grid(row=0, column=1, padx=8, pady=8)

        ttk.Label(dlg, text="Target:").grid(
            row=1, column=0, padx=8, pady=8, sticky="w")
        tgt_var = tk.StringVar()
        ttk.Combobox(dlg, textvariable=tgt_var, values=all_labels,
                     width=30).grid(row=1, column=1, padx=8, pady=8)

        mode = self._mode.get()

        # Type field: mode-dependent
        ttk.Label(dlg, text="Type:").grid(
            row=2, column=0, padx=8, pady=8, sticky="w")
        if mode == "manual":
            type_var = tk.StringVar(value="manual")
            ttk.Label(dlg, text="manual").grid(
                row=2, column=1, padx=8, pady=8, sticky="w")
        else:
            type_var = tk.StringVar(value="deterministic")
            ttk.Combobox(dlg, textvariable=type_var,
                         values=["deterministic", "heuristic"],
                         state="readonly", width=30).grid(
                             row=2, column=1, padx=8, pady=8)

        # Location field
        ttk.Label(dlg, text="Location:").grid(
            row=3, column=0, padx=8, pady=8, sticky="w")
        if mode == "manual":
            loc_options = ["proof", "statement"]
        else:
            loc_options = ["proof", "statement", "inferred"]
        loc_var = tk.StringVar(value=loc_options[0])
        ttk.Combobox(dlg, textvariable=loc_var,
                     values=loc_options,
                     state="readonly", width=30).grid(
                         row=3, column=1, padx=8, pady=8)

        def on_add():
            src = src_var.get().strip()
            tgt = tgt_var.get().strip()
            if not src or not tgt:
                messagebox.showwarning(
                    "Missing",
                    "Both source and target are required.", parent=dlg)
                return
            if src == tgt:
                messagebox.showwarning(
                    "Invalid",
                    "Source and target cannot be the same.", parent=dlg)
                return
            if any(e.source == src and e.target == tgt for e in self._edges):
                messagebox.showwarning(
                    "Duplicate", "This edge already exists.", parent=dlg)
                return
            edge_type = type_var.get()
            loc = loc_var.get()
            self._edges.append(
                DependencyEdge(src, tgt, edge_type, loc, "manual")
            )
            self._cycle_edges = find_cycles(self._edges)
            self._populate_review_tree(tree)
            self._set_status(f"Added edge: {src} -> {tgt}")
            dlg.destroy()

        ttk.Button(dlg, text="Add", command=on_add).grid(
            row=4, column=1, padx=8, pady=8, sticky="e")

        dlg.update_idletasks()
        _center_dialog(dlg, parent)

    # ---- Transitive reduction ----
    def _apply_tred_safe(self, G):
        if self._skip_tred.get():
            return
        import warnings
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                G.tred()
        except Exception:
            logger.warning("Transitive reduction failed", exc_info=True)

    # ---- Preview ----
    def _preview(self):
        if AGraph is None:
            messagebox.showerror("Import error",
                                 "pygraphviz is required for preview.")
            return
        if not self._nodes:
            messagebox.showwarning("No data",
                                   "Load and scan a file first.")
            return
        if not self._env_config:
            messagebox.showwarning("Not configured",
                                   "Configure environments first.")
            return
        if self._edges_mode and self._edges_mode != self._mode.get():
            messagebox.showwarning(
                "Mode mismatch",
                f"Edges were computed in '{self._edges_mode}' mode "
                f"but current mode is '{self._mode.get()}'.\n\n"
                "Please re-configure environments for the new mode."
            )
            return

        view_mode = self._view_mode.get()
        micro_section = (
            self._micro_section.get() if view_mode == "micro" else None
        )

        png_path = None
        map_path = None
        try:
            G = build_graph(
                self._nodes, self._edges, self._env_config,
                self._section_assignments,
                filter_sections=None, filter_envs=None,
                view_mode=view_mode, micro_section=micro_section,
                add_legend=True, cycle_edges=self._cycle_edges,
            )

            self._apply_tred_safe(G)

            G.graph_attr["dpi"] = PREVIEW_DPI

            with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False) as f:
                png_path = f.name
            with tempfile.NamedTemporaryFile(
                    suffix=".cmapx", delete=False) as f:
                map_path = f.name

            G.draw(png_path, prog="dot", format="png")
            G.draw(map_path, prog="dot", format="cmapx")

            if Image is None:
                messagebox.showerror("Preview error",
                                     "Pillow is required.")
                return

            self._base_pil = Image.open(png_path).convert("RGBA")
            self._map_areas = parse_cmapx(map_path)

            self._zoom = 1.0
            self._img_item = None
            self._render_scaled(center=True)
            self._set_status(
                f"Preview rendered: {len(self._map_areas)} clickable areas."
            )

        except Exception as e:
            messagebox.showerror(
                "Preview error",
                "Could not render preview.\n\n" + str(e))
        finally:
            for tmp in (png_path, map_path):
                if tmp is not None:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass

    # ---- Export ----
    def _export(self):
        if not self._nodes:
            messagebox.showwarning("No data",
                                   "Load and scan a file first.")
            return
        if not self._env_config:
            messagebox.showwarning("Not configured",
                                   "Configure environments first.")
            return
        if self._edges_mode and self._edges_mode != self._mode.get():
            messagebox.showwarning(
                "Mode mismatch",
                f"Edges were computed in '{self._edges_mode}' mode "
                f"but current mode is '{self._mode.get()}'.\n\n"
                "Please re-configure environments for the new mode."
            )
            return

        texfile = self._tex_path.get().strip()
        base_dir = os.path.dirname(os.path.abspath(texfile))
        tex_base = os.path.splitext(os.path.basename(texfile))[0]

        from tkinter import simpledialog
        base_name = simpledialog.askstring(
            "Output file name",
            "Enter base name for output files (without extension):",
            initialvalue="dep_graph",
        )
        if not base_name:
            return

        out_dir = os.path.join(base_dir, f"{tex_base}-knowtex")
        os.makedirs(out_dir, exist_ok=True)

        view_mode = self._view_mode.get()
        micro_section = (
            self._micro_section.get() if view_mode == "micro" else None
        )

        try:
            G = build_graph(
                self._nodes, self._edges, self._env_config,
                self._section_assignments,
                filter_sections=None, filter_envs=None,
                view_mode=view_mode, micro_section=micro_section,
                add_legend=True,
                cycle_edges=self._cycle_edges,
            )
            self._apply_tred_safe(G)

            dot_out = os.path.join(out_dir, f"{base_name}.dot")
            with open(dot_out, "w", encoding="utf-8") as f:
                f.write(G.to_string())

            tikz_out = os.path.join(out_dir, f"{base_name}.tex")
            try:
                tikz_code = dot2tex(G.to_string(), format="tikz", crop=True)
                with open(tikz_out, "w", encoding="utf-8") as f:
                    f.write(tikz_code)
            except Exception:
                logger.warning("dot2tex TikZ export failed", exc_info=True)
                tikz_out = "(skipped)"

            png_out = os.path.join(out_dir, f"{base_name}.png")
            try:
                G.graph_attr["dpi"] = EXPORT_DPI
                G.draw(png_out, prog="dot", format="png")
            except Exception:
                logger.warning("PNG export failed", exc_info=True)
                png_out = "(skipped)"

            view_label = (
                f"micro ({micro_section})" if view_mode == "micro"
                else "macro (all)"
            )
            self._set_status(f"Exported to {out_dir} [{view_label}]")
            messagebox.showinfo(
                "Export Complete",
                f"View: {view_label}\n"
                f"Files written to:\n{out_dir}\n\n"
                f"- {base_name}.dot\n"
                f"- {base_name}.tex\n"
                f"- {base_name}.png",
            )

        except Exception as e:
            messagebox.showerror("Export error", str(e))

    # ---- Info panel ----
    def _update_info_panel(self, label):
        ni = self._label_to_info.get(label)
        title = label if not ni else f"{ni.env}   {ni.label}"
        self._info_title.set(title)

        INDEX_RULES = {"H4"}
        deps_from_proof = []
        deps_from_stmt = []
        deps_inferred = []
        deps_index = []
        used_by = []

        for e in self._edges:
            if e.target == label:
                if e.rule in INDEX_RULES:
                    deps_index.append(f"{e.source} ({e.rule})")
                elif e.location == "proof":
                    deps_from_proof.append(e.source)
                elif e.location == "statement":
                    deps_from_stmt.append(e.source)
                elif e.location == "inferred":
                    deps_inferred.append(e.source)
            if e.source == label:
                used_by.append(e.target)

        section = self._section_assignments.get(label, "")

        lines = []
        if section:
            lines.append(f"Section: {section}")
            lines.append("")
        if deps_from_proof:
            lines.append("Dependencies (from proof, solid):")
            lines.extend(
                [f"  - {x}" for x in sorted(set(deps_from_proof))])
            lines.append("")
        if deps_from_stmt:
            lines.append("Dependencies (from statement, dashed):")
            lines.extend(
                [f"  - {x}" for x in sorted(set(deps_from_stmt))])
            lines.append("")
        if deps_inferred:
            lines.append("Dependencies (heuristic, dotted):")
            lines.extend(
                [f"  - {x}" for x in sorted(set(deps_inferred))])
            lines.append("")
        if deps_index:
            lines.append("Dependencies (index-based heuristic):")
            lines.extend(
                [f"  - {x}" for x in sorted(set(deps_index))])
            lines.append("")
        if used_by:
            lines.append("Used by:")
            lines.extend(
                [f"  - {x}" for x in sorted(set(used_by))])
            lines.append("")
        if ni and ni.snippet:
            lines.append("LaTeX snippet:")
            lines.append(ni.snippet.strip()[:SNIPPET_MAX_DISPLAY_LEN])
            lines.append("")
        if not lines:
            lines = ["No extra info available.\n"]

        self._info_text.configure(state="normal")
        self._info_text.delete("1.0", "end")
        self._info_text.insert("1.0", "\n".join(lines))
        self._info_text.configure(state="disabled")

    def _set_status(self, msg):
        self._status.set(msg)
