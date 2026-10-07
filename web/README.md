# KnowTeX Web

The KnowTeX user interface: a single page that loads documents (pasted
text, files or a LaTeX project folder), scans them in infer or manual
mode and draws the dependency graph (force-directed with D3, layered with
viz.js). The built page is `docs/index.html`. It runs in two ways:

- **Published** (GitHub Pages serves the `docs/` folder): the Python core
  runs in the browser through Pyodide; Pyodide, viz.js and D3 are loaded
  from CDNs.
- **Local**: `python -m knowtex serve` (or `python KnowTeX.py`,
  `knowtex-serve`) serves the same `docs/index.html` from
  `knowtex/serve.py` on `127.0.0.1:8765` (`--port`, `--no-browser`,
  `--verbose`). The server injects `window.KNOWTEX_LOCAL`, so the page
  skips Pyodide and sends its calls to `/api/load`, `/api/expand`,
  `/api/structure`, `/api/scan`, `/api/build` and `/api/snippet`, which
  run `knowtex.webapi` natively.
  viz.js and D3 come from `web/vendor/`, so the page works offline. With
  the `export` extra (`pygraphviz`, `dot2tex`, and Graphviz on the
  system) `/api/export` adds a Graphviz PNG of the layered view and a
  TikZ download. The server listens on 127.0.0.1 only and answers just
  its own page: it checks the `Host` header (no DNS rebinding) and, on
  every POST, `Origin`, `Sec-Fetch-Site` and a JSON `Content-Type`, so
  another site open in the same browser cannot send requests to the API
  (see `TestLocalServer` in `test_text_formats.py`).

```bash
python web/build.py                    # bundle knowtex + deps into docs/index.html
python web/build.py --extract DIR      # write the bundled files into DIR instead
python -m knowtex serve                # run the page locally
python web/smoke_test.py               # open it in headless Chromium and check
python web/smoke_test.py --sample latex --screenshot shot.png
python web/smoke_test.py --local --project path/to/latex-project --sweep
```

`build.py` copies the stemmer sources from the installed
`snowballstemmer` package, so it must be installed (`pip install -e
.[web]`). The bundle holds 22 Python files: the knowtex core (including
`structure.py` and `file_expand.py`), `webapi.py` and the English
Snowball stemmer. The LaTeX parser's default engine is a regex pass
(`knowtex/core/parser.py`), so pylatexenc is not bundled.

The page works in steps, each doing only its own work (see
`knowtex/webapi.py`): loading a file or folder stores the document
(`load` / `expand`; the browser reads the files, Python resolves
`\input`, nothing is parsed) and lists its chapters (`structure`, a regex
pass); **Scan** parses the ticked chapters and lists the statement kinds
(`scan`, no edges); **Build graph** infers the edges and draws the graph
(`build`); a click on a node fetches its source (`snippet`). The page
keeps only the document's id; the text never travels back. Inferred edges
are cached per parse and configuration, so display options and edge edits
redraw without rerunning the rules.

`vendor/` holds `viz-global.js` (`@viz-js/viz`) and `d3.min.js`, the
copies the local server serves at `/vendor/`; the published page loads
the same libraries from CDNs instead.

`smoke_test.py` options:

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `--local` | off | serve with the local server (`knowtex.serve`: native Python, vendored libraries) instead of the static `docs/` page (Pyodide, CDN) |
| `--sample {latex,markdown}` | `markdown` | sample loaded by the page |
| `--files FILE ...` | none | load these files through "Browse file…" |
| `--project DIR` | none | load this folder through "Browse folder…" |
| `--sweep` | off | after the graph is built, exercise scope, mode, add/remove edge, the node card, layered view and the download buttons |
| `--screenshot FILE` | none | save a screenshot (`shot.png` and `web/*.png` are gitignored) |
| `--port N` | `0` | local port for serving the page; `0` picks a free port |
| `--timeout S` | `240` | seconds to wait for the runtime |

`template.html` is the page; `/*__PY_BUNDLE__*/` is replaced by the JSON
bundle of Python sources. Rebuild whenever `knowtex/` changes (the local
server imports `knowtex` directly, but serves the built page).

Query parameter: `?sample=latex|markdown` selects the sample loaded at
start.

The page accepts LaTeX and Markdown, the same two formats as the CLI.
Text without Markdown markup is read by the Markdown front-end.

The smoke test needs `pip install playwright && playwright install chromium`
(or `pip install -e .[test]` followed by `playwright install chromium`).
