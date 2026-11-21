# KnowTeX Web

The KnowTeX user interface is a single page, `docs/index.html`, built from `template.html` by `build.py`. It runs in two ways:

- **Published** (GitHub Pages serves `docs/`): the Python core runs in the browser through Pyodide; Pyodide, viz.js and D3 come from CDNs.
- **Local** (`python -m knowtex serve`, `python KnowTeX.py` or `knowtex-serve`): `knowtex/serve.py` serves the same page on `127.0.0.1:8765` and injects `window.KNOWTEX_LOCAL`, so the page skips Pyodide and sends its calls to the `/api/*` endpoints, which run `knowtex.webapi` natively. viz.js and D3 come from `vendor/`, so it works offline. With the `export` extra (`pygraphviz`, `dot2tex`, Graphviz) `/api/export` adds a Graphviz PNG of the layered view and a TikZ download. The server listens on 127.0.0.1 only and checks the `Host`, `Origin`, `Sec-Fetch-Site` and `Content-Type` headers, so another site open in the same browser cannot call the API (`TestLocalServer` in `tests/test_text_formats.py`).

```bash
python web/build.py                    # bundle knowtex/ and the stemmer into docs/index.html
python web/build.py --extract DIR      # write the bundled files into DIR instead
python -m knowtex serve                # run the page locally
python web/smoke_test.py               # open the page in headless Chromium and check it
python web/smoke_test.py --local --project path/to/latex-project --sweep
```

**Build.** `build.py` replaces `/*__PY_BUNDLE__*/` in `template.html` with a JSON bundle of the `knowtex/` sources, `webapi.py` and the English Snowball stemmer copied from the installed `snowballstemmer` package (`pip install -e .[web]`). Rebuild whenever `knowtex/` changes: the local server imports `knowtex` directly but serves the built page. The LaTeX parser's default engine is a regex pass, so pylatexenc is not bundled.

**How the page works** (`knowtex/webapi.py`). Loading a file or folder stores the document and lists its chapters (`load` / `expand` / `structure`; the browser reads the files, Python resolves `\input`, nothing is parsed yet). **Scan** parses the ticked chapters and lists the statement kinds (`scan`). **Build graph** infers the edges and draws the graph (`build`); a click on a node fetches its source (`snippet`). The page keeps only the document's id, and inferred edges are cached per parse and configuration, so display options and edge edits redraw without rerunning the rules. `?sample=latex|markdown` selects the sample loaded at start.

**Smoke test.** `smoke_test.py` needs `pip install -e .[test]` followed by `playwright install chromium`. By default it tests the static `docs/` page (Pyodide, CDN); `--local` tests the local server. `--sample`, `--files`, `--project` choose the input, `--sweep` exercises scope, mode, edge edits, the node card, the layered view and the downloads, `--screenshot FILE` saves a screenshot (`shot.png` and `web/*.png` are gitignored). `--help` lists the options.
