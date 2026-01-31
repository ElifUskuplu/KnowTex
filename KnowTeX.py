#!/usr/bin/env python3
# KnowTeX_clickable.py

import os
import re
import tempfile
from collections import defaultdict, namedtuple
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET

try:
    from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode
    from pygraphviz import AGraph
    from dot2tex import dot2tex
    from PIL import Image, ImageTk  # for zoomable preview
except Exception as e:
    LatexWalker = None
    LatexEnvironmentNode = None
    AGraph = None
    dot2tex = None
    Image = None
    ImageTk = None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None

# ----------------------
# Canonical categories and alias patterns
# ----------------------
CANONICAL_ORDER = [
    "definition",
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "construction",
    "example",
    "remark",
]

ALIASES = {
    "definition":   re.compile(r"^(definition|defn|def)$", re.I),
    "theorem":      re.compile(r"^(theorem|thm|th|thrm)$", re.I),
    "lemma":        re.compile(r"^(lemma|lem|ilemma|alemma)$", re.I),
    "proposition":  re.compile(r"^(proposition|propn|prop|prp)$", re.I),
    "corollary":    re.compile(r"^(corollary|cor|corol|corl)$", re.I),
    "construction": re.compile(r"^(construction|constn|const|constr)$", re.I),
    "example":      re.compile(r"^(example|examples|iexample)$", re.I),
    "remark":       re.compile(r"^(remark|remarks)$", re.I),
}

PROOF_ALIAS_RX = re.compile(r"^(proof|pr|pf|prf|pfof|pfoftheorem)$", re.I)

def canonical_of_env(envname: str):
    for canon, rx in ALIASES.items():
        if rx.fullmatch(envname):
            return canon
    return None

NodeInfo = namedtuple("NodeInfo", "canon env label index snippet")

SHAPES = {
    "theorem": "doublecircle",
    "definition": "box",
    "proposition": "diamond",
    "lemma": "ellipse",
    "corollary": "ellipse",
    "construction": "diamond",
    "example": "ellipse",
    "remark": "ellipse",
}
BORDERCOLOR = {
    "theorem": "Blue",
    "definition": "Purple",
    "proposition": "Blue",
    "lemma": "Blue",
    "corollary": "Blue",
    "construction": "Purple",
    "example": "DimGray",
    "remark": "DimGray",
}
FILLCOLOR = {
    "theorem": "SkyBlue",
    "definition": "Lavender",
    "proposition": "SkyBlue",
    "lemma": "SkyBlue",
    "corollary": "White",
    "construction": "White",
    "example": "White",
    "remark": "White",
}

# ----------------------
# Regex for content and includes
# ----------------------
LABEL_RX   = re.compile(r"\\label\{([^}]+)\}")
USES_RX    = re.compile(r"\\uses\{([^}]*)\}")
PROVES_RX  = re.compile(r"\\proves\{([^}]*)\}")
INPUT_BRACED_RX     = re.compile(r"\\input\s*\{([^}]+)\}")
INPUT_SPACEFORM_RX  = re.compile(r"\\input\s+([^\s%]+)")
INCLUDE_RX          = re.compile(r"\\include\s*\{([^}]+)\}")
INCLUDEONLY_RX      = re.compile(r"\\includeonly\s*\{([^}]*)\}")
IMPORT_RX           = re.compile(r"\\import\s*\{([^}]+)\}\s*\{([^}]+)\}")
SUBIMPORT_RX        = re.compile(r"\\subimport\s*\{([^}]+)\}\s*\{([^}]+)\}")
COMMENT_RX          = re.compile(r"(^|[^\\])%.*")

# Chapter detection (supports optional short titles and starred)
CHAPTER_RX = re.compile(r"\\chapter\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", re.M)

# ----------------------
# Helpers
# ----------------------

def strip_comments(text: str) -> str:
    return re.sub(COMMENT_RX, lambda m: m.group(1), text)

def ensure_tex_ext(path: str) -> str:
    return path if os.path.splitext(path)[1] else path + ".tex"

def norm_join(base_dir: str, rel: str) -> str:
    return os.path.normpath(os.path.join(base_dir, rel))

def point_in_poly(x: float, y: float, poly):
    # Ray casting, poly: list[(x,y)]
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

# ----------------------
# Project expansion (files)
# ----------------------

def load_and_expand(main_path: str) -> str:
    visited = set()

    def collect_includeonly(text: str):
        incs = set()
        for m in INCLUDEONLY_RX.finditer(strip_comments(text)):
            names = [x.strip() for x in m.group(1).split(",") if x.strip()]
            incs.update(names)
        return incs

    def read_file(p: str) -> str:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()

    main_path = os.path.abspath(main_path)
    project_dir = os.path.dirname(main_path)
    main_text = read_file(main_path)
    includeonly = collect_includeonly(main_text)

    def expand(path: str, current_dir: str) -> str:
        abs_path = os.path.abspath(path)
        if abs_path in visited:
            return ""
        visited.add(abs_path)

        try:
            raw = read_file(abs_path)
        except FileNotFoundError:
            return f"% [depgraph] missing file: {abs_path}\n"

        text = strip_comments(raw)

        def repl_import(m):
            inc_dir = norm_join(current_dir, m.group(1))
            inc_path = ensure_tex_ext(norm_join(inc_dir, m.group(2)))
            return expand(inc_path, inc_dir)
        text = IMPORT_RX.sub(repl_import, text)
        text = SUBIMPORT_RX.sub(repl_import, text)

        def repl_input_braced(m):
            rel = m.group(1).strip()
            inc_path = ensure_tex_ext(norm_join(current_dir, rel))
            inc_dir = os.path.dirname(inc_path)
            return expand(inc_path, inc_dir)
        text = INPUT_BRACED_RX.sub(repl_input_braced, text)

        def repl_input_space(m):
            rel = m.group(1).strip()
            inc_path = ensure_tex_ext(norm_join(current_dir, rel))
            inc_dir = os.path.dirname(inc_path)
            return expand(inc_path, inc_dir)
        text = INPUT_SPACEFORM_RX.sub(repl_input_space, text)

        def repl_include(m):
            name = m.group(1).strip()
            base_name = os.path.basename(name)
            if includeonly and (base_name not in includeonly):
                return f"% [depgraph] skipped by \\includeonly: {name}\n"
            inc_path = ensure_tex_ext(norm_join(current_dir, name))
            inc_dir = os.path.dirname(inc_path)
            return expand(inc_path, inc_dir)
        text = INCLUDE_RX.sub(repl_include, text)

        return text

    return expand(main_path, project_dir)

# ----------------------
# Chapters helpers
# ----------------------

def find_chapter_ranges(tex: str):
    matches = list(CHAPTER_RX.finditer(tex))
    if not matches:
        return []
    chapters = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.start()
        end = matches[i+1].start() if (i+1) < len(matches) else len(tex)
        chapters.append({"title": title, "start": start, "end": end})
    return chapters

# ----------------------
# Parsing
# ----------------------

def parse_latex_structure(tex, selected_canonicals):
    lw = LatexWalker(tex)
    nodelist, _, _ = lw.get_latex_nodes()

    nodes = []
    node_by_index = {}
    label_to_node = {}
    uses_on_node = defaultdict(list)
    proofs = []

    order_counter = 0
    last_stmt_idx = None

    def walk(n):
        nonlocal order_counter, last_stmt_idx

        if isinstance(n, LatexEnvironmentNode):
            env = n.environmentname
            canon = canonical_of_env(env)

            if (canon is not None) and (canon in selected_canonicals):
                my_index = order_counter
                order_counter += 1
                last_stmt_idx = my_index

                try:
                    snippet = tex[n.pos:n.pos_end]
                except Exception:
                    snippet = n.latex_verbatim()

                s = snippet
                m = LABEL_RX.search(s)
                lbl = m.group(1) if m else None
                label = lbl if lbl else f"{env}:{my_index}"

                ni = NodeInfo(canon=canon, env=env, label=label, index=my_index, snippet=snippet)
                nodes.append(ni)
                node_by_index[my_index] = ni
                if lbl:
                    label_to_node[lbl] = ni

                for um in USES_RX.finditer(s):
                    labels = [x.strip() for x in um.group(1).split(",") if x.strip()]
                    if labels:
                        uses_on_node[my_index].extend(labels)

            elif PROOF_ALIAS_RX.fullmatch(env or ""):
                my_index = order_counter
                order_counter += 1
                s = n.latex_verbatim()

                pm = PROVES_RX.search(s)
                target_label = pm.group(1).strip() if pm else None

                used = []
                for um in USES_RX.finditer(s):
                    used += [x.strip() for x in um.group(1).split(",") if x.strip()]

                proofs.append({
                    "index": my_index,
                    "target_label": target_label,
                    "uses": used,
                    "target_node_idx": last_stmt_idx,
                })

            for ch in (n.nodelist or []):
                walk(ch)
        else:
            if hasattr(n, "nodelist") and n.nodelist:
                for ch in n.nodelist:
                    walk(ch)

    for root in nodelist:
        walk(root)

    for p in proofs:
        if p["target_label"] and p["target_label"] in label_to_node:
            p["target_node_idx"] = label_to_node[p["target_label"]].index

    return nodes, node_by_index, label_to_node, uses_on_node, proofs

# ----------------------
# Graph building
# ----------------------

def build_graph(nodes, node_by_index, label_to_node, uses_on_node, proofs):
    G = AGraph(directed=True, bgcolor="transparent")
    G.node_attr["penwidth"] = 1.8
    G.edge_attr.update(arrowhead="vee")

    for ni in nodes:
        k = ni.canon
        # URL forces Graphviz to emit map areas (cmapx)
        G.add_node(
            ni.label,
            label=ni.label.split(":")[-1],
            shape=SHAPES.get(k, "ellipse"),
            style="filled",
            color=BORDERCOLOR.get(k, "black"),
            fillcolor=FILLCOLOR.get(k, "white"),
            URL=ni.label,
            tooltip=ni.label,
        )

    for idx, labels in uses_on_node.items():
        target_node = node_by_index.get(idx)
        if not target_node:
            continue
        target_label = target_node.label
        for lbl in labels:
            src = label_to_node.get(lbl)
            if src:
                G.add_edge(src.label, target_label, style="dashed")

    for p in proofs:
        tgt_idx = p.get("target_node_idx")
        if tgt_idx is None:
            continue
        target_node = node_by_index.get(tgt_idx)
        if not target_node:
            continue
        target_label = target_node.label
        for lbl in p["uses"]:
            src = label_to_node.get(lbl)
            if src:
                G.add_edge(src.label, target_label)

    return G

# ----------------------
# GUI
# ----------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KnowTeX: Knowledge Dependency from TeX")
        # Start maximized (platform-aware)
        try:
            self.state("zoomed")      # Windows
        except tk.TclError:
            self.attributes("-zoomed", True)   # Linux

        if _IMPORT_ERROR:
            messagebox.showerror(
                "Import error",
                "One or more required packages failed to import:\n\n"
                f"{_IMPORT_ERROR}\n\n"
                "Please install: pygraphviz, dot2tex, pylatexenc, Pillow\n"
                "and ensure Graphviz is installed and on PATH."
            )

        self.tex_path = tk.StringVar()
        self.nonreduced = tk.BooleanVar(value=False)
        self.canon_vars = {canon: tk.BooleanVar(value=True) for canon in CANONICAL_ORDER}

        self._chapter_ranges = None
        self._filtered_tex = None

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Main .tex file:").pack(side="left")
        ttk.Entry(top, textvariable=self.tex_path, width=70).pack(side="left", padx=6)
        ttk.Button(top, text="Browse…", command=self.browse_tex).pack(side="left")
        ttk.Checkbutton(top, text="Keep all edges (nonreduced)", variable=self.nonreduced).pack(side="left", padx=12)

        envs_frame = ttk.LabelFrame(self, text="Include categories", padding=8)
        envs_frame.pack(fill="x", padx=8, pady=8)
        labels = {
            "definition": "Definition",
            "theorem": "Theorem",
            "lemma": "Lemma",
            "proposition": "Proposition",
            "corollary": "Corollary",
            "construction": "Construction",
            "example": "Example",
            "remark": "Remark",
        }
        for i, canon in enumerate(CANONICAL_ORDER):
            ttk.Checkbutton(envs_frame, text=labels[canon], variable=self.canon_vars[canon]).grid(
                row=0, column=i, padx=6, pady=2, sticky="w"
            )

        btns = ttk.Frame(self, padding=8)
        btns.pack(fill="x")
        ttk.Button(btns, text="Scan", command=self.scan).pack(side="left")
        ttk.Button(btns, text="Generate DOT + TikZ", command=self.generate).pack(side="left", padx=8)
        ttk.Button(btns, text="Preview", command=self.preview).pack(side="left")

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

        self.preview_frame = ttk.Frame(self, padding=8)
        self.preview_frame.pack(fill="both", expand=True)

        toolbar = ttk.Frame(self.preview_frame)
        toolbar.pack(fill="x", side="top")
        ttk.Button(toolbar, text="Zoom -", command=lambda: self._zoom_by(0.9)).pack(side="left")
        ttk.Button(toolbar, text="Zoom +", command=lambda: self._zoom_by(1.111111)).pack(side="left")
        ttk.Button(toolbar, text="Fit", command=self._zoom_fit).pack(side="left", padx=(8,0))
        ttk.Button(toolbar, text="100%", command=self._zoom_reset).pack(side="left")

        pw = ttk.Panedwindow(self.preview_frame, orient="horizontal")
        pw.pack(fill="both", expand=True)

        canvas_frame = ttk.Frame(pw)
        info_frame = ttk.Frame(pw, padding=8)
        pw.add(canvas_frame, weight=4)
        pw.add(info_frame, weight=1)

        self.canvas = tk.Canvas(canvas_frame, bg="#fafafa")
        xscroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        yscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.pack(fill="both", expand=True, side="left")
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")

        ttk.Label(info_frame, text="Selection").pack(anchor="w")
        self.info_title = tk.StringVar(value="Click a node")
        ttk.Label(info_frame, textvariable=self.info_title, wraplength=260).pack(anchor="w", pady=(2,8))

        self.info_text = tk.Text(info_frame, height=30, wrap="word")
        self.info_text.pack(fill="both", expand=True)
        self.info_text.insert("1.0", "No node selected.\n")
        self.info_text.configure(state="disabled")

        self._photo = None
        self._expanded_tex = None
        self._nodes = None
        self._node_by_index = None
        self._label_to_node = None
        self._uses_on_node = None
        self._proofs = None

        self._label_to_info = {}
        self._rev_uses = defaultdict(set)
        self._rev_proof = defaultdict(set)

        # Click map from Graphviz cmapx
        # list of dicts: {"label": ..., "shape": "poly"/"rect"/"circle", "coords": [...]}
        self._map_areas = []

        self._mouse_down = None
        self._highlight_item = None

        self._base_pil = None
        self._zoom = 1.0
        self._img_item = None

        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)
        self.canvas.bind("<Control-MouseWheel>", self._on_wheel)
        self.canvas.bind("<Command-MouseWheel>", self._on_wheel)
        self.canvas.bind("<Control-Button-4>", lambda e: self._wheel_compat(+120))
        self.canvas.bind("<Control-Button-5>", lambda e: self._wheel_compat(-120))

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down, add="+")
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up, add="+")

    def browse_tex(self):
        path = filedialog.askopenfilename(
            title="Select main .tex file",
            filetypes=[("TeX files", "*.tex"), ("All files", "*.*")],
        )
        if path:
            self.tex_path.set(path)

    def _selected_canonicals(self):
        return {c for c, var in self.canon_vars.items() if var.get()}

    def _expand(self):
        texfile = self.tex_path.get().strip()
        if not texfile:
            messagebox.showwarning("Missing file", "Please choose a main .tex file first.")
            return None
        try:
            self.status.set("Expanding project…")
            self.update_idletasks()
            return load_and_expand(texfile)
        except Exception as e:
            messagebox.showerror("Error while expanding", str(e))
            return None

    def _choose_chapters_from_tex(self, expanded_tex: str):
        chapters = find_chapter_ranges(expanded_tex)
        if not chapters:
            return None

        win = tk.Toplevel(self)
        win.title("Select chapters to scan")
        win.geometry("480x440")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Choose the chapters to include:").pack(anchor="w", padx=10, pady=(10,6))

        outer = ttk.Frame(win)
        outer.pack(fill="both", expand=True, padx=10, pady=6)
        canvas = tk.Canvas(outer, borderwidth=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        vars_ = []
        for i, ch in enumerate(chapters, 1):
            v = tk.BooleanVar(value=True)
            text = f"{i}. {ch['title']}"
            ttk.Checkbutton(inner, text=text, variable=v).pack(anchor="w", pady=2)
            vars_.append(v)

        selected_ranges = []

        def on_ok():
            for v, ch in zip(vars_, chapters):
                if v.get():
                    selected_ranges.append((ch['start'], ch['end']))
            win.destroy()

        def on_all():
            for v in vars_:
                v.set(True)

        def on_none():
            for v in vars_:
                v.set(False)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="All", command=on_all).pack(side="left")
        ttk.Button(btns, text="None", command=on_none).pack(side="left", padx=6)
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right")

        self.wait_window(win)
        return selected_ranges

    def scan(self):
        if _IMPORT_ERROR:
            messagebox.showerror("Import error", str(_IMPORT_ERROR))
            return

        expanded = self._expand()
        if expanded is None:
            return
        self._expanded_tex = expanded

        self._chapter_ranges = self._choose_chapters_from_tex(expanded)
        if self._chapter_ranges is None:
            self._filtered_tex = expanded
            self.status.set("No chapters found; scanning whole document…")
        else:
            if len(self._chapter_ranges) == 0:
                self._filtered_tex = ""
                self.status.set("No chapters selected; result will be empty.")
            else:
                parts = []
                for (s, e) in self._chapter_ranges:
                    parts.append(expanded[s:e])
                    parts.append("\n\n% [chapter-slice separator]\n\n")
                self._filtered_tex = "".join(parts)
                self.status.set(f"Scanning {len(self._chapter_ranges)} selected chapter(s)…")

        try:
            selected = self._selected_canonicals()
            (nodes,
             node_by_index,
             label_to_node,
             uses_on_node,
             proofs) = parse_latex_structure(self._filtered_tex, selected)
        except Exception as e:
            messagebox.showerror("Parse error", str(e))
            return

        self._nodes = nodes
        self._node_by_index = node_by_index
        self._label_to_node = label_to_node
        self._uses_on_node = uses_on_node
        self._proofs = proofs

        self._label_to_info = {ni.label: ni for ni in nodes}

        self._rev_uses = defaultdict(set)
        for idx, labels in uses_on_node.items():
            tgt = node_by_index.get(idx)
            if not tgt:
                continue
            for lbl in labels:
                src = label_to_node.get(lbl)
                if src:
                    self._rev_uses[src.label].add(tgt.label)

        self._rev_proof = defaultdict(set)
        for p in proofs:
            tgt_idx = p.get("target_node_idx")
            if tgt_idx is None:
                continue
            tgt = node_by_index.get(tgt_idx)
            if not tgt:
                continue
            for lbl in p.get("uses", []):
                src = label_to_node.get(lbl)
                if src:
                    self._rev_proof[src.label].add(tgt.label)

        counts = defaultdict(int)
        for n in nodes:
            counts[n.canon] += 1
        display_names = {
            "definition": "Definition",
            "theorem": "Theorem",
            "lemma": "Lemma",
            "proposition": "Proposition",
            "corollary": "Corollary",
            "construction": "Construction",
            "example": "Example",
            "remark": "Remark",
        }
        pretty = []
        selected = self._selected_canonicals()
        for canon in CANONICAL_ORDER:
            if canon in selected:
                pretty.append(f"{display_names[canon]}:{counts.get(canon,0)}")
        self.status.set("Found: " + ", ".join(pretty) if pretty else "No selected categories found.")

    def _build_graph(self):
        if _IMPORT_ERROR:
            messagebox.showerror("Import error", str(_IMPORT_ERROR))
            return None

        if self._expanded_tex is None:
            expanded = self._expand()
            if expanded is None:
                return None
            self._expanded_tex = expanded
            if self._filtered_tex is None:
                self._filtered_tex = expanded
            selected = self._selected_canonicals()
            (nodes,
             node_by_index,
             label_to_node,
             uses_on_node,
             proofs) = parse_latex_structure(self._filtered_tex, selected)
            self._nodes, self._node_by_index = nodes, node_by_index
            self._label_to_node, self._uses_on_node, self._proofs = label_to_node, uses_on_node, proofs

            self._label_to_info = {ni.label: ni for ni in nodes}
            self._rev_uses = defaultdict(set)
            for idx, labels in uses_on_node.items():
                tgt = node_by_index.get(idx)
                if not tgt:
                    continue
                for lbl in labels:
                    src = label_to_node.get(lbl)
                    if src:
                        self._rev_uses[src.label].add(tgt.label)

            self._rev_proof = defaultdict(set)
            for p in proofs:
                tgt_idx = p.get("target_node_idx")
                if tgt_idx is None:
                    continue
                tgt = node_by_index.get(tgt_idx)
                if not tgt:
                    continue
                for lbl in p.get("uses", []):
                    src = label_to_node.get(lbl)
                    if src:
                        self._rev_proof[src.label].add(tgt.label)

        try:
            G = build_graph(self._nodes, self._node_by_index, self._label_to_node, self._uses_on_node, self._proofs)
            if not self.nonreduced.get():
                G.tred()
            return G
        except Exception as e:
            messagebox.showerror("Graph error", str(e))
            return None

    def generate(self):
        G = self._build_graph()
        if G is None:
            return

        base_dir = os.path.dirname(os.path.abspath(self.tex_path.get()))

        from tkinter import simpledialog
        base_name = simpledialog.askstring(
            "Output file name",
            "Enter base name for output files (without extension):",
            initialvalue="dep_graph"
        )
        if not base_name:
            return

        dot_path  = os.path.join(base_dir, f"{base_name}.dot")
        tikz_path = os.path.join(base_dir, f"{base_name}.tex")

        try:
            with open(dot_path, "w", encoding="utf-8") as f:
                f.write(G.to_string())
            tikz_code = dot2tex(G.to_string(), format="tikz", crop=True)
            with open(tikz_path, "w", encoding="utf-8") as f:
                f.write(tikz_code)
        except Exception as e:
            messagebox.showerror("Write error", str(e))
            return

        self.status.set(f"DOT -> {dot_path}  TikZ -> {tikz_path}")
        messagebox.showinfo("Generated", f"Wrote:\n{dot_path}\n{tikz_path}")

    # ---------- PREVIEW with Graphviz cmapx for accurate clicking ----------
    def preview(self):
        G = self._build_graph()
        if G is None:
            return

        try:
            # Fix dpi so PNG and map coordinates match
            G.graph_attr["dpi"] = "96"

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                png_path = f.name
            with tempfile.NamedTemporaryFile(suffix=".cmapx", delete=False) as f:
                map_path = f.name

            # Draw both outputs from the same graph settings
            G.draw(png_path, prog="dot", format="png")
            G.draw(map_path, prog="dot", format="cmapx")
        except Exception as e:
            messagebox.showerror(
                "Preview error",
                "Could not render preview. Ensure Graphviz is installed.\n\n" + str(e))
            return

        if Image is None:
            messagebox.showerror("Preview error", "Pillow is required for zoomable preview. Please install the 'Pillow' package.")
            return

        try:
            self._base_pil = Image.open(png_path).convert("RGBA")
        except Exception as e:
            messagebox.showerror("Preview error", f"Failed to load PNG into Tkinter:\n{e}")
            return

        # Parse cmapx for exact clickable regions
        self._map_areas = []
        try:
            text = open(map_path, "r", encoding="utf-8", errors="ignore").read()
            # cmapx is HTML-ish; wrap into a root for XML parsing
            # It typically looks like: <map id="G" name="G"> ... <area ... /> ... </map>
            m = re.search(r"(<map\b.*?</map>)", text, flags=re.S | re.I)
            if m:
                map_xml = m.group(1)
                root = ET.fromstring("<root>" + map_xml + "</root>")
                for area in root.iter("area"):
                    shape = (area.attrib.get("shape") or "").lower()
                    coords_s = area.attrib.get("coords") or ""
                    href = area.attrib.get("href") or ""
                    title = area.attrib.get("title") or ""
                    # We stored URL=label, so href should be that label
                    lbl = href or title
                    if not lbl or not coords_s:
                        continue
                    coords = [int(float(c)) for c in coords_s.split(",") if c.strip()]
                    self._map_areas.append({"label": lbl, "shape": shape, "coords": coords})
        except Exception:
            # Fallback: no map; clicks will do nothing rather than be wrong
            self._map_areas = []

        self._zoom = 1.0
        self._render_scaled(center=True)
        self.status.set(f"Preview: {png_path}")

    def _render_scaled(self, center=False, pivot=None):
        if self._base_pil is None:
            return
        w0, h0 = self._base_pil.size
        w = max(1, int(round(w0 * self._zoom)))
        h = max(1, int(round(h0 * self._zoom)))

        pil = self._base_pil.resize((w, h), Image.LANCZOS)
        img = ImageTk.PhotoImage(pil)
        self._photo = img

        if self._img_item is None:
            self.canvas.delete("all")
            self._img_item = self.canvas.create_image(0, 0, image=img, anchor="nw")
            self._highlight_item = None
        else:
            self.canvas.itemconfigure(self._img_item, image=img)

        self.canvas.configure(scrollregion=(0, 0, w, h))

        if center:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            self.canvas.xview_moveto(max(0, (w - cw) / 2) / max(1, w))
            self.canvas.yview_moveto(max(0, (h - ch) / 2) / max(1, h))
        elif pivot is not None:
            cx, cy = pivot
            bx = (self.canvas.canvasx(cx)) / max(1, w)
            by = (self.canvas.canvasy(cy)) / max(1, h)
            self.canvas.xview_moveto(max(0.0, min(1.0, bx - (self.canvas.winfo_width()/2)/max(1, w))))
            self.canvas.yview_moveto(max(0.0, min(1.0, by - (self.canvas.winfo_height()/2)/max(1, h))))

        # Drop highlight on re-render
        if self._highlight_item is not None:
            self.canvas.delete(self._highlight_item)
            self._highlight_item = None

    def _zoom_by(self, factor, pivot=None):
        new_zoom = self._zoom * factor
        new_zoom = max(0.05, min(8.0, new_zoom))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        self._zoom = new_zoom
        self._render_scaled(pivot=pivot)
        self.status.set(f"Zoom: {int(round(self._zoom*100))}%")

    def _zoom_fit(self):
        if self._base_pil is None:
            return
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        w0, h0 = self._base_pil.size
        if w0 == 0 or h0 == 0:
            return
        margin = 0.95
        self._zoom = max(0.05, min(8.0, margin * min(cw / w0, ch / h0)))
        self._render_scaled(center=True)
        self.status.set(f"Zoom: {int(round(self._zoom*100))}% (Fit)")

    def _zoom_reset(self):
        self._zoom = 1.0
        self._render_scaled(center=True)
        self.status.set("Zoom: 100%")

    def _pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_wheel(self, event):
        factor = 1.111111 if event.delta > 0 else 0.9
        self._zoom_by(factor, pivot=(event.x, event.y))

    def _wheel_compat(self, delta):
        factor = 1.111111 if delta > 0 else 0.9
        cx, cy = self.canvas.winfo_width()//2, self.canvas.winfo_height()//2
        self._zoom_by(factor, pivot=(cx, cy))

    # ---------- click handlers ----------
    def _on_mouse_down(self, event):
        self._mouse_down = (event.x, event.y)

    def _on_mouse_up(self, event):
        if self._mouse_down is None:
            return
        x0, y0 = self._mouse_down
        dx = abs(event.x - x0)
        dy = abs(event.y - y0)
        self._mouse_down = None
        if dx > 4 or dy > 4:
            return
        self._handle_click(event)

    def _handle_click(self, event):
        if not self._map_areas:
            return

        ix = self.canvas.canvasx(event.x)
        iy = self.canvas.canvasy(event.y)
        x = ix / max(1e-9, self._zoom)
        y = iy / max(1e-9, self._zoom)

        hit = None
        for area in self._map_areas:
            shape = area["shape"]
            coords = area["coords"]
            if shape == "rect" and len(coords) >= 4:
                l, t, r, b = coords[:4]
                if l <= x <= r and t <= y <= b:
                    hit = area["label"]
                    break
            elif shape == "circle" and len(coords) >= 3:
                cx, cy, rad = coords[:3]
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= rad * rad:
                    hit = area["label"]
                    break
            elif shape == "poly" and len(coords) >= 6:
                pts = [(coords[i], coords[i+1]) for i in range(0, len(coords) - 1, 2)]
                if point_in_poly(x, y, pts):
                    hit = area["label"]
                    break

        if not hit:
            return

        ni = self._label_to_info.get(hit)
        if ni:
            messagebox.showinfo("Node", f"{ni.canon.title()}   {ni.label}")
        else:
            messagebox.showinfo("Node", hit)

        self._update_info_panel(hit)
        self._highlight_from_map(hit)

    def _update_info_panel(self, label):
        ni = self._label_to_info.get(label)
        title = label if not ni else f"{ni.canon.title()}   {ni.label}"
        self.info_title.set(title)

        deps = []
        if ni and self._uses_on_node is not None:
            deps.extend(self._uses_on_node.get(ni.index, []))

        proof_deps = []
        if ni and self._proofs is not None:
            for p in self._proofs:
                if p.get("target_node_idx") == ni.index:
                    proof_deps.extend(p.get("uses", []))

        used_by = sorted(self._rev_uses.get(label, set()) | self._rev_proof.get(label, set()))

        snippet = ""
        if ni and ni.snippet:
            snippet = ni.snippet.strip()

        lines = []
        if deps:
            lines.append("Depends on (uses):")
            lines.extend([f"  - {x}" for x in sorted(set(deps))])
            lines.append("")
        if proof_deps:
            lines.append("Proof uses:")
            lines.extend([f"  - {x}" for x in sorted(set(proof_deps))])
            lines.append("")
        if used_by:
            lines.append("Used by:")
            lines.extend([f"  - {x}" for x in used_by])
            lines.append("")
        if snippet:
            lines.append("LaTeX snippet:")
            lines.append(snippet)
            lines.append("")

        if not lines:
            lines = ["No extra info available.\n"]

        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", "\n".join(lines))
        self.info_text.configure(state="disabled")

    def _highlight_from_map(self, label):
        # Find first matching area and highlight its bounding box
        target = None
        for area in self._map_areas:
            if area["label"] == label:
                target = area
                break
        if not target:
            return

        shape = target["shape"]
        coords = target["coords"]

        if shape == "rect" and len(coords) >= 4:
            l, t, r, b = coords[:4]
        elif shape == "circle" and len(coords) >= 3:
            cx, cy, rad = coords[:3]
            l, t, r, b = cx - rad, cy - rad, cx + rad, cy + rad
        elif shape == "poly" and len(coords) >= 6:
            xs = coords[0::2]
            ys = coords[1::2]
            l, r = min(xs), max(xs)
            t, b = min(ys), max(ys)
        else:
            return

        lz, tz, rz, bz = l * self._zoom, t * self._zoom, r * self._zoom, b * self._zoom

        if self._highlight_item is not None:
            try:
                self.canvas.delete(self._highlight_item)
            except Exception:
                pass
            self._highlight_item = None

        self._highlight_item = self.canvas.create_rectangle(lz, tz, rz, bz, outline="red", width=3)

# ----------------------
# Entrypoint
# ----------------------

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
