"""Zoomable, pannable canvas with Graphviz cmapx click handling."""

import logging
import re

from knowtex.core.constants import (
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP_IN, ZOOM_STEP_OUT,
    ZOOM_FIT_MARGIN, CLICK_DRAG_THRESHOLD, SNIPPET_MAX_DISPLAY_LEN,
)
from knowtex.core.utils import point_in_poly

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import defusedxml.ElementTree as SafeET
except ImportError:
    import xml.etree.ElementTree as SafeET

logger = logging.getLogger("knowtex")


def parse_cmapx(map_path):
    """Parse a Graphviz cmapx file into a list of clickable area dicts.

    Returns list of {"label": str, "shape": str, "coords": list[int]}.
    """
    areas = []
    try:
        with open(map_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        m = re.search(r"(<map\b.*?</map>)", text, flags=re.S | re.I)
        if m:
            map_xml = m.group(1)
            root = SafeET.fromstring("<root>" + map_xml + "</root>")
            for area in root.iter("area"):
                shape = (area.attrib.get("shape") or "").lower()
                coords_s = area.attrib.get("coords") or ""
                href = area.attrib.get("href") or ""
                title = area.attrib.get("title") or ""
                lbl = href or title
                if not lbl or not coords_s or lbl == "__legend__":
                    continue
                coords = [
                    int(float(c))
                    for c in coords_s.split(",") if c.strip()
                ]
                areas.append({
                    "label": lbl, "shape": shape, "coords": coords
                })
    except Exception:
        logger.warning("Failed to parse cmapx image map", exc_info=True)
    return areas


class PreviewMixin:
    """Mixin providing zoomable/pannable canvas with cmapx click handling.

    The host class must have:
      - self._canvas: tk.Canvas
      - self._status: tk.StringVar (or self.status)
      - self._info_title: tk.StringVar
      - self._info_text: tk.Text
      - self._label_to_info: dict (label -> NodeInfo)
    """

    def _init_preview_state(self):
        """Initialize preview state variables. Call in __init__."""
        self._base_pil = None
        self._zoom = 1.0
        self._photo = None
        self._img_item = None
        self._map_areas = []
        self._mouse_down = None
        self._highlight_item = None

    def _bind_canvas_events(self):
        """Bind zoom, pan, and click events to the canvas."""
        self._canvas.bind("<ButtonPress-1>", self._pan_start)
        self._canvas.bind("<B1-Motion>", self._pan_move)
        self._canvas.bind("<Control-MouseWheel>", self._on_wheel)
        self._canvas.bind("<Command-MouseWheel>", self._on_wheel)
        self._canvas.bind(
            "<Control-Button-4>", lambda _e: self._wheel_compat(+120)
        )
        self._canvas.bind(
            "<Control-Button-5>", lambda _e: self._wheel_compat(-120)
        )
        self._canvas.bind("<ButtonPress-1>", self._on_mouse_down, add="+")
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_up, add="+")

    def _render_scaled(self, center=False, pivot=None):
        """Display PIL image on canvas at current zoom level."""
        if self._base_pil is None:
            return
        w0, h0 = self._base_pil.size
        w = max(1, int(round(w0 * self._zoom)))
        h = max(1, int(round(h0 * self._zoom)))

        pil = self._base_pil.resize((w, h), Image.LANCZOS)
        img = ImageTk.PhotoImage(pil)
        self._photo = img

        if self._img_item is None:
            self._canvas.delete("all")
            self._img_item = self._canvas.create_image(
                0, 0, image=img, anchor="nw"
            )
            self._highlight_item = None
        else:
            self._canvas.itemconfigure(self._img_item, image=img)

        self._canvas.configure(scrollregion=(0, 0, w, h))

        if center:
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            self._canvas.xview_moveto(max(0, (w - cw) / 2) / max(1, w))
            self._canvas.yview_moveto(max(0, (h - ch) / 2) / max(1, h))
        elif pivot is not None:
            cx, cy = pivot
            bx = self._canvas.canvasx(cx) / max(1, w)
            by = self._canvas.canvasy(cy) / max(1, h)
            self._canvas.xview_moveto(
                max(0.0, min(1.0,
                    bx - (self._canvas.winfo_width() / 2) / max(1, w)))
            )
            self._canvas.yview_moveto(
                max(0.0, min(1.0,
                    by - (self._canvas.winfo_height() / 2) / max(1, h)))
            )

        if self._highlight_item is not None:
            self._canvas.delete(self._highlight_item)
            self._highlight_item = None

    def _zoom_by(self, factor, pivot=None):
        new_zoom = self._zoom * factor
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        self._zoom = new_zoom
        self._render_scaled(pivot=pivot)
        self._set_status(f"Zoom: {int(round(self._zoom * 100))}%")

    def _zoom_fit(self):
        if self._base_pil is None:
            return
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        w0, h0 = self._base_pil.size
        if w0 == 0 or h0 == 0:
            return
        self._zoom = max(
            ZOOM_MIN,
            min(ZOOM_MAX, ZOOM_FIT_MARGIN * min(cw / w0, ch / h0)),
        )
        self._render_scaled(center=True)
        self._set_status(f"Zoom: {int(round(self._zoom * 100))}% (Fit)")

    def _zoom_reset(self):
        self._zoom = 1.0
        self._render_scaled(center=True)
        self._set_status("Zoom: 100%")

    def _pan_start(self, event):
        self._canvas.scan_mark(event.x, event.y)

    def _pan_move(self, event):
        self._canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_wheel(self, event):
        factor = ZOOM_STEP_IN if event.delta > 0 else ZOOM_STEP_OUT
        self._zoom_by(factor, pivot=(event.x, event.y))

    def _wheel_compat(self, delta):
        factor = ZOOM_STEP_IN if delta > 0 else ZOOM_STEP_OUT
        cx = self._canvas.winfo_width() // 2
        cy = self._canvas.winfo_height() // 2
        self._zoom_by(factor, pivot=(cx, cy))

    def _on_mouse_down(self, event):
        self._mouse_down = (event.x, event.y)

    def _on_mouse_up(self, event):
        if self._mouse_down is None:
            return
        x0, y0 = self._mouse_down
        dx = abs(event.x - x0)
        dy = abs(event.y - y0)
        self._mouse_down = None
        if dx > CLICK_DRAG_THRESHOLD or dy > CLICK_DRAG_THRESHOLD:
            return
        self._handle_click(event)

    def _handle_click(self, event):
        if not self._map_areas:
            return

        ix = self._canvas.canvasx(event.x)
        iy = self._canvas.canvasy(event.y)
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
                if (x - cx) ** 2 + (y - cy) ** 2 <= rad * rad:
                    hit = area["label"]
                    break
            elif shape == "poly" and len(coords) >= 6:
                pts = [
                    (coords[i], coords[i + 1])
                    for i in range(0, len(coords) - 1, 2)
                ]
                if point_in_poly(x, y, pts):
                    hit = area["label"]
                    break

        if not hit:
            return

        self._update_info_panel(hit)
        self._highlight_from_map(hit)

    def _highlight_from_map(self, label):
        """Draw red rectangle around clicked node."""
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

        lz = l * self._zoom
        tz = t * self._zoom
        rz = r * self._zoom
        bz = b * self._zoom

        if self._highlight_item is not None:
            try:
                self._canvas.delete(self._highlight_item)
            except Exception:
                pass
            self._highlight_item = None

        self._highlight_item = self._canvas.create_rectangle(
            lz, tz, rz, bz, outline="red", width=3
        )

    def _set_status(self, msg):
        """Set status bar text. Override in subclass if needed."""
        if hasattr(self, "_status"):
            self._status.set(msg)
        elif hasattr(self, "status"):
            self.status.set(msg)
