"""Local server: the web page with native Python behind it.

    python -m knowtex serve [--port N] [--no-browser]

Serves docs/index.html (the same page GitHub Pages serves) and answers
its /api/ calls with ``knowtex.webapi`` running in this interpreter, so
no Python runtime is downloaded and large projects run at native speed.
viz.js and D3 are served from web/vendor, so the page works offline.
Exports that need Graphviz (PNG, TikZ via dot2tex) are offered when the
packages are installed.

The server listens on 127.0.0.1 only and answers just its own page: every
request must carry a Host header naming this server (no DNS rebinding),
and every POST must come from the page itself (Origin and Sec-Fetch-Site,
when the browser sends them, must be same-origin, and the body must be
JSON), so another site open in the same browser cannot drive the API.
"""

import argparse
import base64
import json
import os
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from knowtex import webapi

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "index.html"
VENDOR = ROOT / "web" / "vendor"

API = {"load": webapi.load, "expand": webapi.expand, "structure": webapi.structure,
       "scan": webapi.scan, "build": webapi.build, "snippet": webapi.snippet}

LOCAL_HOSTS = ("127.0.0.1", "localhost")
MAX_BODY = 128 * 1024 * 1024        # bytes; a whole LaTeX project as JSON


def capabilities():
    caps = {"png": False, "tex": False, "svg": False}
    try:
        import pygraphviz  # noqa: F401
        caps["png"] = caps["svg"] = True
    except ImportError:
        pass
    try:
        import dot2tex  # noqa: F401
        caps["tex"] = caps["png"]      # dot2tex needs the dot binary too
    except ImportError:
        pass
    return caps


def export(dot, fmt):
    """Render DOT with Graphviz: "png"/"svg" (bytes) or "tex" (TikZ text)."""
    from pygraphviz import AGraph
    if fmt in ("png", "svg"):
        G = AGraph(string=dot)
        G.graph_attr["dpi"] = "150"
        with tempfile.NamedTemporaryFile(suffix="." + fmt, delete=False) as f:
            path = f.name
        try:
            G.draw(path, prog="dot", format=fmt)
            return open(path, "rb").read()
        finally:
            os.unlink(path)
    if fmt == "tex":
        from dot2tex import dot2tex
        return dot2tex(dot, format="tikz", crop=True).encode("utf-8")
    raise ValueError(f"unknown export format {fmt!r}")


class Handler(BaseHTTPRequestHandler):
    server_version = "KnowTeX/0.2"

    def log_message(self, fmt, *args):      # quiet unless --verbose
        if self.server.verbose:
            super().log_message(fmt, *args)

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _origins(self):
        port = self.server.server_address[1]
        return {f"http://{h}:{port}" for h in LOCAL_HOSTS}

    def _host_ok(self):
        """The Host header names this server (blocks DNS rebinding)."""
        host = (self.headers.get("Host") or "").strip().lower()
        return "http://" + host in self._origins()

    def _post_ok(self):
        """A POST comes from our own page: same-origin and JSON.  Browsers
        send Origin and Sec-Fetch-Site on every cross-site request, so a
        request lacking them comes from a non-browser client (tests, curl)."""
        if not self._host_ok():
            return False
        origin = (self.headers.get("Origin") or "").strip().lower()
        if origin and origin not in self._origins():
            return False
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if site and site not in ("same-origin", "none"):
            return False
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        return ctype == "application/json"

    def _forbid(self, why):
        self._send(403, json.dumps({"ok": False, "error": why}).encode())

    def do_GET(self):
        if not self._host_ok():
            return self._forbid("bad Host header")
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = PAGE.read_text(encoding="utf-8")
            inject = ("<script>window.KNOWTEX_LOCAL = "
                      + json.dumps({"capabilities": capabilities()}) + ";</script>")
            html = html.replace("<head>", "<head>\n" + inject, 1)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if path.startswith("/vendor/"):
            name = os.path.basename(path)
            f = VENDOR / name
            if f.is_file():
                return self._send(200, f.read_bytes(), "application/javascript")
        if path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "capabilities": capabilities()}).encode())
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._post_ok():
            return self._forbid("cross-site request refused: the API answers "
                                "only its own page (same origin, JSON body)")
        path = self.path.split("?", 1)[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= MAX_BODY:
            return self._send(413, b'{"ok": false, "error": "request too large"}')
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, b'{"ok": false, "error": "bad JSON"}')
        if not isinstance(req, dict):
            return self._send(400, b'{"ok": false, "error": "bad JSON"}')
        name = path.rsplit("/", 1)[-1]
        if path.startswith("/api/") and name in API:
            out = API[name](*req.get("args", []))
            return self._send(200, out.encode("utf-8"))
        if path == "/api/export":
            try:
                data = export(req.get("dot", ""), req.get("format", "png"))
                return self._send(200, json.dumps({
                    "ok": True, "format": req.get("format"),
                    "data": base64.b64encode(data).decode("ascii")}).encode())
            except Exception as e:
                return self._send(200, json.dumps({"ok": False, "error": str(e)}).encode())
        self._send(404, b'{"ok": false, "error": "unknown endpoint"}')


def serve(port=0, open_browser=True, verbose=False):
    if not PAGE.is_file():
        sys.exit(f"{PAGE} is missing; run python web/build.py first")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.verbose = verbose
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"KnowTeX at {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="knowtex serve", description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765, help="0 picks a free port")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="log every request")
    args = ap.parse_args(argv)
    serve(args.port, open_browser=not args.no_browser, verbose=args.verbose)


if __name__ == "__main__":
    main()
