#!/usr/bin/env python3
"""Headless-browser smoke test for the web page.

Serves the page, opens it in Chromium (Playwright), waits for the runtime
and the graph, then reports node/edge counts and console errors.

Usage:
    python web/smoke_test.py [--local] [--sample latex|markdown]
                             [--files a.md b.md ...] [--project DIR]
                             [--sweep] [--screenshot out.png] [--timeout S]

    --local     serve with "python -m knowtex serve" (native Python, vendored
                libraries) instead of the static docs/ page (Pyodide, CDN)
    --files     load these files through "Browse file…"
    --project   load this folder through "Browse folder…"
    --sweep     after the graph is built, exercise scope, mode, add/remove
                edge, layered view and the download buttons
Requires:  pip install playwright && playwright install chromium
"""

import argparse
import http.server
import os
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT))


def serve_static(directory, port):
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **k)
    socketserver.TCPServer.allow_reuse_address = True   # must precede bind()
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def serve_local(port):
    from http.server import ThreadingHTTPServer
    from knowtex.serve import Handler
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.verbose = False
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


JS_STATE = """() => ({
  status: document.getElementById('status').dataset.state,
  text: document.getElementById('status-text').textContent,
  edges: document.getElementById('edge-count').textContent,
  nodes: document.getElementById('node-count').textContent,
  gnodes: document.querySelectorAll('#stage svg g.node').length || document.querySelectorAll('#force .fnode').length,
  gedges: document.querySelectorAll('#stage svg g.edge').length || document.querySelectorAll('#force .flink').length,
  ghosts: document.querySelectorAll('#force .fnode.ghost').length,
  ranges: document.querySelectorAll('#ranges-list input.rng').length,
  envs: document.querySelectorAll('#env-table input.inc').length,
  unordered: document.getElementById('loaded').dataset.unordered === '1',
  loaded: !document.getElementById('loaded').hidden ? document.getElementById('loaded-name').textContent : '',
  error: document.getElementById('error').hidden ? '' : document.getElementById('error').textContent,
})"""
IDLE = "() => document.getElementById('status').dataset.state !== 'busy'"
GRAPH = "() => document.querySelector('#stage svg') !== null || document.querySelectorAll('#force .fnode').length > 0 || document.getElementById('status').dataset.state === 'error'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--sample", default="markdown", choices=("latex", "markdown"))
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--screenshot", default=None)
    ap.add_argument("--port", type=int, default=0, help="0 picks a free port")
    ap.add_argument("--timeout", type=int, default=240, help="seconds to wait for the runtime")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    httpd = serve_local(args.port) if args.local else serve_static(DOCS, args.port)
    port = httpd.server_address[1]
    loading_files = args.files is not None or args.project
    url = f"http://127.0.0.1:{port}/" + ("" if loading_files else f"?sample={args.sample}")
    errors, logs = [], []
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("console", lambda m: (logs.append(f"[{m.type}] {m.text}"),
                                      errors.append(m.text) if m.type == "error" else None))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)

        def wait_idle(t=60_000):
            page.wait_for_function(IDLE, timeout=t)

        def wait_graph(t=60_000):
            page.wait_for_function(GRAPH, timeout=t)

        def state():
            return page.evaluate(JS_STATE)

        def check(cond, msg):
            nonlocal ok
            if not cond:
                ok = False
                print("FAIL:", msg)
            else:
                print("ok:", msg)

        try:
            wait_idle(args.timeout * 1000)
            if args.files is not None:
                page.set_input_files("#file-input", [str(Path(f).resolve()) for f in args.files])
                page.wait_for_function("() => !document.getElementById('loaded').hidden", timeout=args.timeout * 1000)
                wait_idle(args.timeout * 1000)
                st = state()
                check(st["loaded"] != "", f"files loaded: {st['loaded']}")
                if len(args.files) > 1:
                    check(st["unordered"], "several files -> no reading order")
            elif args.project:
                page.set_input_files("#folder-input", str(Path(args.project).resolve()))
                page.wait_for_function("() => !document.getElementById('loaded').hidden", timeout=args.timeout * 1000)
                wait_idle(args.timeout * 1000)
                st = state()
                check(st["loaded"] != "", f"project loaded: {st['loaded']}")
                check(st["ranges"] > 0, f"{st['ranges']} chapter/section ranges listed")
                if st["nodes"] == "0" and "Build graph" in st["text"]:
                    # big document: keep the theorem-like kinds only, then build
                    page.evaluate("""() => { for (const i of document.querySelectorAll('#env-table input.inc')) i.checked = ['definition','theorem','lemma','corollary','proposition'].includes(i.dataset.env); }""")
                    page.click("#build")
            wait_graph(args.timeout * 1000)
            wait_idle(args.timeout * 1000)
            st = state()
            print("status:", st["status"], "|", st["text"])
            print("counts:", {k: st[k] for k in ("nodes", "edges", "gnodes", "gedges", "envs")})
            check(st["status"] == "ready" and int(st["nodes"]) > 0 and st["gnodes"] > 0, "graph drawn")
            if st["error"]:
                check(False, "page error box: " + st["error"][:400])

            if args.sweep:
                # scope: pick the first section, expect ghosts or fewer nodes
                if page.evaluate("() => !document.getElementById('scope-wrap').hidden"):
                    page.select_option("#opt-scope", index=1); wait_idle(); page.wait_for_timeout(300)
                    st2 = state()
                    check(int(st2["nodes"]) <= int(st["nodes"]), f"scope: {st2['nodes']} nodes drawn, {st2['ghosts']} external")
                    page.select_option("#opt-scope", ""); wait_idle()
                else:
                    print("skip: no sections for the scope test")
                # add an edge between the first two labels, then remove it
                page.click(".tab[data-tab=edges]"); page.wait_for_timeout(100)
                before = int(state()["edges"])
                page.evaluate("() => { const s = document.getElementById('add-src'), t = document.getElementById('add-tgt'); s.selectedIndex = 0; t.selectedIndex = t.options.length - 1; }")
                page.click("#add-edge button[type=submit]"); wait_idle(); page.wait_for_timeout(200)
                after = int(state()["edges"])
                check(after == before + 1 or state()["error"], f"add edge: {before} -> {after}")
                page.click("#edge-table button.x[data-added='1']"); wait_idle(); page.wait_for_timeout(200)
                check(int(state()["edges"]) == before, "remove the added edge")
                # remove a real edge and restore (the count may not drop by one:
                # an edge that was redundant only through the removed one comes back)
                first = page.evaluate("() => { const b = document.querySelector(\"#edge-table button.x:not([data-added='1'])\"); return [b.dataset.s, b.dataset.t]; }")
                page.click("#edge-table button.x:not([data-added='1'])"); wait_idle(); page.wait_for_timeout(200)
                gone = page.evaluate("([s, t]) => ![...document.querySelectorAll('#edge-table button.x')].some(b => b.dataset.s === s && b.dataset.t === t)", first)
                check(gone, f"remove the inferred edge {first[0]} -> {first[1]}")
                page.click("#restore"); wait_idle(); page.wait_for_timeout(200)
                check(int(state()["edges"]) == before, "restore removed edges")
                # manual mode and back
                page.click("#mode-seg button[data-mode=manual]"); wait_idle(); page.wait_for_timeout(200)
                check(state()["status"] == "ready", f"manual mode: {state()['edges']} edges")
                page.click("#mode-seg button[data-mode=infer]"); wait_idle(); page.wait_for_timeout(200)
                check(int(state()["edges"]) == before, "back to infer mode")
                # layered view
                page.click(".tab[data-tab=graph]"); page.wait_for_timeout(100)
                page.select_option("#opt-view", "layered"); wait_idle(); page.wait_for_timeout(500)
                check(page.evaluate("() => !!document.querySelector('#stage svg')"), "layered (Graphviz) view rendered")
                # downloads
                for bid in ("dl-svg", "dl-png", "dl-dot"):
                    with page.expect_download(timeout=15_000) as dl:
                        page.click("#" + bid)
                    check(dl.value.suggested_filename.startswith("knowtex-graph"), f"download {bid}: {dl.value.suggested_filename}")
                if page.evaluate("() => !document.getElementById('dl-tex').hidden"):
                    with page.expect_download(timeout=30_000) as dl:
                        page.click("#dl-tex")
                    check(dl.value.suggested_filename.endswith(".tex"), "download TikZ")
        except Exception as e:
            ok = False
            print("TIMEOUT/ERROR:", e)
        if args.screenshot:
            page.evaluate("() => window.scrollTo(0, 0)")
            page.screenshot(path=args.screenshot, full_page=False)
            print("screenshot:", args.screenshot)
        browser.close()
    httpd.shutdown()
    if errors:
        print("console errors:")
        for e in errors[:20]:
            print("  ", e[:300])
        ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
