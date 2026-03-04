"""GUI dialog classes: environment configuration, range selection, edge editing."""

import tkinter as tk
from tkinter import ttk, colorchooser

from knowtex.core.constants import SHAPE_OPTIONS, PRESET_COLORS, DEFN_ENV_RX


def _center_dialog(dialog, parent):
    """Center a dialog on its parent window, ensuring it fits on screen."""
    dialog.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    px = parent.winfo_x()
    py = parent.winfo_y()

    dw = dialog.winfo_reqwidth()
    dh = dialog.winfo_reqheight()

    min_w, min_h = dialog.minsize()
    if min_w > 0:
        dw = max(min_w, dw)
    if min_h > 0:
        dh = max(min_h, dh)

    sw = dialog.winfo_screenwidth()
    sh = dialog.winfo_screenheight()
    dw = min(dw, sw)
    dh = min(dh, sh)

    x = px + (pw - dw) // 2
    y = py + (ph - dh) // 2
    x = max(0, min(x, sw - dw))
    y = max(0, min(y, sh - dh))

    dialog.geometry(f"{dw}x{dh}+{x}+{y}")


class EnvConfigDialog(tk.Toplevel):
    """Dialog for configuring environment inclusion, shapes, and colors.

    When show_is_defn=True, an extra 'Is Defn' checkbox column is shown
    (used by infer mode for D4 term matching).
    """

    def __init__(self, parent, discovered_envs, show_is_defn=False):
        super().__init__(parent)
        self.title("Environment Configuration")
        self.transient(parent)
        self.grab_set()

        self.result = None
        self._env_names = sorted(discovered_envs)
        self._rows = {}
        self._show_is_defn = show_is_defn

        self.minsize(750, 450)

        ttk.Label(
            self,
            text="Configure inclusion, shape, and colors for each "
                 "environment type.\nUnchecked environments will be "
                 "excluded from the graph entirely.",
            wraplength=700,
        ).pack(padx=10, pady=(10, 6), anchor="w")

        # Scrollable frame
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=10, pady=6)
        canvas = tk.Canvas(outer, borderwidth=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Header row
        col = 0
        ttk.Label(inner, text="Include", font=("", 10, "bold")).grid(
            row=0, column=col, padx=8, pady=4, sticky="w")
        col += 1
        ttk.Label(inner, text="Environment", font=("", 10, "bold")).grid(
            row=0, column=col, padx=8, pady=4, sticky="w")
        col += 1
        ttk.Label(inner, text="Shape", font=("", 10, "bold")).grid(
            row=0, column=col, padx=8, pady=4, sticky="w")
        col += 1
        ttk.Label(inner, text="Border Color", font=("", 10, "bold")).grid(
            row=0, column=col, padx=8, pady=4, sticky="w")
        col += 1
        ttk.Label(inner, text="Fill Color", font=("", 10, "bold")).grid(
            row=0, column=col, padx=8, pady=4, sticky="w")
        if show_is_defn:
            col += 1
            ttk.Label(inner, text="Is Defn", font=("", 10, "bold")).grid(
                row=0, column=col, padx=8, pady=4, sticky="w")

        # Data rows
        for i, env_name in enumerate(self._env_names, start=1):
            include_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(inner, variable=include_var).grid(
                row=i, column=0, padx=8, pady=3)

            ttk.Label(inner, text=env_name).grid(
                row=i, column=1, padx=8, pady=3, sticky="w")

            shape_var = tk.StringVar(value="ellipse")
            ttk.Combobox(
                inner, textvariable=shape_var,
                values=SHAPE_OPTIONS, state="readonly", width=14,
            ).grid(row=i, column=2, padx=8, pady=3)

            border_var = tk.StringVar(value="Blue")
            border_frame = ttk.Frame(inner)
            border_frame.grid(row=i, column=3, padx=8, pady=3)
            ttk.Combobox(
                border_frame, textvariable=border_var,
                values=PRESET_COLORS, width=10,
            ).pack(side="left")
            ttk.Button(
                border_frame, text="...", width=3,
                command=lambda v=border_var: self._pick_color(v),
            ).pack(side="left", padx=2)

            fill_var = tk.StringVar(value="White")
            fill_frame = ttk.Frame(inner)
            fill_frame.grid(row=i, column=4, padx=8, pady=3)
            ttk.Combobox(
                fill_frame, textvariable=fill_var,
                values=PRESET_COLORS, width=10,
            ).pack(side="left")
            ttk.Button(
                fill_frame, text="...", width=3,
                command=lambda v=fill_var: self._pick_color(v),
            ).pack(side="left", padx=2)

            row_data = {
                "include_var": include_var,
                "shape_var": shape_var,
                "border_var": border_var,
                "fill_var": fill_var,
            }

            if show_is_defn:
                is_defn_var = tk.BooleanVar(
                    value=bool(DEFN_ENV_RX.fullmatch(env_name))
                )
                ttk.Checkbutton(inner, variable=is_defn_var).grid(
                    row=i, column=5, padx=8, pady=3)
                row_data["is_defn_var"] = is_defn_var

            self._rows[env_name] = row_data

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="OK", command=self._on_ok).pack(
            side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self._on_cancel).pack(
            side="right")

        _center_dialog(self, parent)

    def _pick_color(self, var):
        color = colorchooser.askcolor(title="Choose color", parent=self)
        if color and color[1]:
            var.set(color[1])

    def _on_ok(self):
        self.result = {}
        for env_name, row in self._rows.items():
            entry = {
                "include": row["include_var"].get(),
                "shape": row["shape_var"].get(),
                "border": row["border_var"].get(),
                "fill": row["fill_var"].get(),
            }
            if self._show_is_defn and "is_defn_var" in row:
                entry["is_defn"] = row["is_defn_var"].get()
            self.result[env_name] = entry
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()
