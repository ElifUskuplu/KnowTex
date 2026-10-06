# KnowTeX: Knowledge Dependency from TeX

**KnowTeX** is a Python tool that reads LaTeX projects or Markdown notes and constructs **knowledge dependency graphs** among mathematical statements and proofs.
It comes as a browser page (run locally or on GitHub Pages) and a command-line tool; it expands your TeX project, parses the document structure, extracts the statements, and visualizes how results depend on one another.

Derived from [Patrick Massot's *plastexdepgraph* plugin](https://github.com/PatrickMassot/plastexdepgraph), KnowTeX provides similar functionality **without requiring PlasTeX or Lean blueprints**.

**Artificial Intelligence Disclosure (AID)**

Portions of the KnowTeX project were developed with the assistance of generative AI tools (Claude). These tools were used to help draft Python code, suggest refactoring patterns, and improve documentation clarity. All generated code was reviewed, tested, and validated by the author, who assumes full responsibility for the final implementation and design decisions.

---

## Two Modes of Operation

KnowTeX offers two complementary modes for constructing dependency graphs:

### Manual Mode

Uses explicit **annotation commands** that authors embed in their LaTeX source:

- `\uses{label1,label2,...}` -- declares that the current statement or proof depends on the listed labels.
- `\proves{label}` -- declares that the current proof establishes a particular labeled statement.

Edges from `\uses{}` in a **statement** appear as **dashed arrows**; edges from `\uses{}` in a **proof** appear as **solid arrows**. If `\proves{}` is omitted, the proof is assumed to prove the most recent statement.

### Infer Mode

Automatically infers dependencies by analyzing the document content using a layered system of **deterministic rules** and **heuristic rules**:

| Rule | Type | Description |
| ---- | ---- | ----------- |
| **D1** | Deterministic | `\ref`/`\Cref`/`\eqref` inside a **proof** creates an edge to the proved statement |
| **D2** | Deterministic | `\ref`/`\Cref`/`\eqref` inside a **statement** creates an edge to the referencing statement |
| **D3** | Deterministic | Explicit proof target from `\begin{proof}[Proof of Theorem \ref{...}]` |
| **D4** | Deterministic | **Defined-term matching** -- terms introduced via `\emph{}`/`\textit{}`/`\textbf{}` or `\index{}` in definition environments are matched in subsequent statements via stemming |
| **H1** | Heuristic | Each proof is associated with the nearest preceding statement |
| **H2** | Heuristic | A corollary without any `\ref` is linked to the nearest preceding theorem/proposition |
| **H3** | Heuristic | A lemma is linked to the next theorem/proposition within a 3-statement gap (`H3_MAX_GAP` in `constants.py`) |
| **H4** | Heuristic | **Index/emphasis-term matching** (LaTeX input only) -- `\index{}` entries and emphasized terms (`\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`) of non-definition statements are matched in later statements using longest-match-first strategy with `\|see{}` alias resolution |

---

## Input Formats

KnowTeX reads two kinds of input. The inference rules are the same for all of them; only the front-end that finds statements, defined terms and references differs.

| Format | Statements | Defined terms (D4) | References (D1/D2) |
| ------ | ---------- | ------------------ | ------------------ |
| **LaTeX** (`.tex`, projects with `\input`) | theorem-like environments | `\emph{}`, `\textit{}`, `\textbf{}`, `\index{}` | `\ref`, `\Cref`, `\cref`, `\eqref` |
| **Markdown** (`.md`) | `## Theorem 2.1 (Name)` headings or `**Definition 2.1.**` paragraphs; `Proof.` … `∎` | `**bold**`, the parenthesized name, "quoted" and "called a …" phrases | `[text](#label)`, `[text](…/slug)`, textual "Theorem 2.1" |

A Markdown file with no keyword blocks at all is treated as a glossary: every heading (or YAML `title:`) is a definition entry whose title is the defined term. This is how the MathGloss corpus is read directly, without any conversion to LaTeX (`benchmark/chicago_benchmark.py`).

Labels are taken from `\label{}` / `{#label}`, otherwise from the number (`theorem:2.1`), the name, the first defined term, or a running index.

## Command Line

```bash
python -m knowtex.cli notes.md                    # print inferred edges
python -m knowtex.cli main.tex --dot graph.dot    # write Graphviz DOT
python -m knowtex.cli notes.md --json out.json    # nodes and edges as JSON
python -m knowtex.cli main.tex --mode manual      # \uses{} annotations only
cat notes.md | python -m knowtex.cli -            # read from stdin
```

After `pip install -e .` the same command is available as `knowtex`; `python -m knowtex notes.md ...` also runs it (without a file argument, `python -m knowtex` starts the local server).

| Option | Meaning |
| ------ | ------- |
| `path` | input file, or `-` for stdin; a `.tex`/`.ltx` main file is expanded (`\input`, `\include`, ...) |
| `--format {auto,latex,markdown}` | input format (default `auto`: file extension, otherwise content detection) |
| `--mode {infer,manual}` | inference rules (default) or `\uses{}` annotations |
| `--definition-env ENV` | environment treated as definition-like for D4 (repeatable; default: names such as `definition`, `defn`, `notation`, `axiom`, see `DEFN_ENV_RX`) |
| `--no-tred` | skip transitive reduction (applied by default) |
| `--dot FILE` | write Graphviz DOT |
| `--json FILE` | write nodes and edges as JSON |
| `--quiet` | do not print the summary and the edge list |

The JSON file has this shape:

```json
{
  "format": "latex",
  "nodes": [{"label": "def:ring", "env": "definition", "index": 0, "name": "ring"}],
  "edges": [{"source": "def:ring", "target": "lem:ring-unit", "rule": "D4",
             "type": "deterministic", "location": "statement"}]
}
```

## Web Page (local or GitHub Pages)

The page `docs/index.html` is KnowTeX's user interface. It runs the same Python code either in the browser through [Pyodide](https://pyodide.org) or on a local Python server, draws the layered graph with [viz.js](https://github.com/mdaines/viz-js) and the default interactive force-directed view with D3 (drag nodes, hover to see a node's neighbours, click a node to keep only its prerequisites and/or dependents up to a chosen depth). See [Usage](#usage) for the controls.

- Local server: `python KnowTeX.py` (or `python -m knowtex serve`) serves the page with native Python and the libraries in `web/vendor/`, so it works offline and large projects run at native speed. With `pip install -e .[export]` (and Graphviz on the system) it also offers Graphviz PNG and TikZ downloads.
- Hosted copy: enable GitHub Pages for this repository (Settings → Pages → *Deploy from a branch*, branch `main`, folder `/docs`); the page is then served at `https://<user>.github.io/KnowTex/`. It loads Pyodide (about 10 MB, cached after the first visit), viz.js and D3 from CDNs. Nothing leaves the browser.
- Rebuild after changing the core: `python web/build.py` (bundles `knowtex/`, a subset of `pylatexenc` and the English Snowball stemmer into `docs/index.html`; needs `pylatexenc` and `snowballstemmer` installed, e.g. `pip install -e .[web]`). `python web/smoke_test.py` checks the page in headless Chromium (`--local` for the local server). See `web/README.md`.

## Features

- **LaTeX project expansion**: follows `\input`, `\include`, `\import`, `\subimport`, `\subfile`, and `\includeonly`.
- **Document class detection**: supports both `book`-class (chapters) and `article`-class (sections) documents.
- **Environment recognition**: detects canonical mathematical environments and their aliases (see table below).
- **Defined-term extraction**: extracts terms from `\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`, and `\index{}` entries; uses Snowball stemming for language-aware matching.
- **Cycle detection**: identifies cyclic dependencies using Tarjan's SCC algorithm and highlights them in red.
- **Cycle resolution**: in infer mode, term-match (D4) edges that close a cycle are dropped, weakest evidence first, until only cycles made of the author's own references remain (`infer.resolve_cycles`; `--keep-cycles` in the CLI skips it). The dropped edges are reported.
- **Transitive reduction**: removes redundant edges (on by default; edges inside a cycle are always kept). The CLI and the web page use the same pure-Python implementation (`cycles.transitive_reduction`).
- **Macro/Micro views**: macro view shows the full graph; micro view focuses on a single section/chapter.
- **Output formats**:
  - **Graphviz DOT** (`.dot`)
  - **SVG** and **PNG** of the current view
  - **TikZ** (`.tex` via `dot2tex`, local server only)
- **Web page features**:
  - Chapter/section checklist for LaTeX documents
  - Per-environment inclusion toggles with customizable shapes, border colors, and fill colors
  - Force-directed and layered views with zoom/pan and "Fit"
  - Edge table with remove/restore and an "Add edge" form

---

## Supported Environments

KnowTeX automatically discovers all `\begin{...}...\end{...}` theorem-like environments in the scanned LaTeX project. Well-known non-theorem environments (e.g. `figure`, `equation`, `align`, `tikzpicture`, etc.) are skipped.

After scanning, the environment table on the web page lets users:

- **Include/exclude** each discovered environment from the graph.
- Choose **shape**, **border color**, and **fill color** per environment.
- In Infer mode, mark which environments are **definition-like** (used by the D4 defined-term matching rule).

Available shape options: `ellipse`, `circle`, `doublecircle`, `box`, `diamond`, `triangle`, `pentagon`, `hexagon`, `octagon`.
Colors are picked with the browser's color chooser.

---

## Project Structure

```text
KnowTex/
├── KnowTeX.py              # Entry point: starts the local server and opens the page
├── pyproject.toml          # Package metadata, dependencies, console scripts
├── LICENSE
├── knowtex/
│   ├── __main__.py          # `python -m knowtex`: local server, or the CLI when given a file
│   ├── cli.py               # Command-line interface
│   ├── serve.py             # Local server: serves the page, answers its /api/ calls
│   ├── webapi.py            # JSON entry points used by the page (Pyodide or local server)
│   ├── core/
│   │   ├── constants.py     # Regex patterns, skip sets, thresholds
│   │   ├── data.py          # Data classes: NodeInfo, ProofInfo, DependencyEdge
│   │   ├── parser.py        # LaTeX parsing and environment extraction
│   │   ├── file_expand.py   # \input/\include/\subfile expansion
│   │   ├── structure.py     # Document class, chapter/section detection
│   │   ├── dot.py           # DOT builder used by the CLI and the page (no pygraphviz)
│   │   ├── formats.py       # Input format detection and dispatch
│   │   ├── text_parser.py   # Markdown front-end
│   │   ├── cycles.py        # Tarjan's SCC cycle detection, transitive reduction
│   │   └── utils.py         # Utility functions
│   └── deps/
│       ├── manual.py        # Manual mode: \uses{}/\proves{} extraction
│       ├── infer.py         # Infer mode: D1-D4, H2-H4 rules (format-independent), cycle resolution
│       ├── term_extraction.py  # Stemming and term extraction for D4/H4
│       └── index_registry.py   # \index{} and emphasized-term registry for H4
├── test_knowtex.py          # Test suite (pytest)
├── test_text_formats.py    # Tests for the Markdown/text front-end, DOT, reduction
├── web/                    # Page template, build script, smoke test
│   └── vendor/             # viz.js and D3, served by the local server (offline)
├── docs/index.html         # Built page (served by GitHub Pages and the local server)
├── benchmark/              # MathGloss Chicago Notes benchmark
├── BCT-condensed/          # Case study: manual vs. infer mode on Basic Category Theory
├── Polynomial-Freiman-Ruzsa/  # Case study: manual vs. infer mode on PFR
└── example/                 # Example LaTeX files with and without annotations
```

---

## Installation

**Requirements**

- Python >= 3.10
- Packages (declared in `pyproject.toml`):
  ```bash
  pip install -e .            # core: pylatexenc, PyStemmer (enough for the CLI and the local server)
  pip install -e .[export]    # + pygraphviz, dot2tex (PNG and TikZ exports from the local server)
  pip install -e .[web]       # + snowballstemmer (rebuild docs/index.html)
  pip install -e .[test]      # + pytest, playwright (tests, web smoke test)
  # PyStemmer can be replaced by the pure-Python 'snowballstemmer' (same algorithm)
  ```
  This installs two commands: `knowtex` (CLI) and `knowtex-serve` (local server).
- [Graphviz](https://graphviz.org/download/) (must be on system `PATH`; only for the `export` extra)

**Linux**
```bash
sudo apt install graphviz libgraphviz-dev
```
**macOS**
```bash
brew install graphviz
```
**Windows**
Install Graphviz and add `Graphviz/bin` to your PATH.

---

## Usage

### 1. Start the page
```bash
python KnowTeX.py        # or: python -m knowtex, python -m knowtex serve, or knowtex-serve after pip install
```

This starts a small local server (`knowtex/serve.py`) on `http://127.0.0.1:8765/` and opens the page in your browser. Options: `--port N` (`0` picks a free port), `--no-browser`, `--verbose`. Stop it with Ctrl-C. The same page works without installing anything on GitHub Pages (see [Web Page](#web-page-local-or-github-pages)).

### 2. Load a document

- Paste a document, or press one of the **LaTeX** / **Markdown** sample buttons.
- **Browse file…**: one `.tex` or `.md` file, or several `.md` files. Several Markdown files are read in file-name order with a blank line between files, as one glossary with no reading order: D4 then matches a defined term in every other entry instead of only in later ones; no other rule changes.
- **Browse folder…**: a LaTeX project. The browser reads the folder (with its subfolders) and KnowTeX expands all `\input` / `\include` / `\subfile` / `\import` files in memory. If several files contain `\documentclass`, a **Main file** select appears; missing files are listed as notes.
- For LaTeX, a checklist of chapters (book classes) or sections (article class) selects what to scan.
- A Markdown file is read as a single file: no `\input` expansion, no chapter/section list, and no index registry (H4).

### 3. Configure

- Select **Infer** or **Manual** mode (edges from the author's `\uses{}` annotations only). Infer is the default.
- The environment table has one row per statement kind: **Include**, **Definition** (Infer mode: the definition-like kinds used by D4), **Shape**, **Border** and **Fill** colour.
- **Scope**: the whole document, or one chapter/section; statements of other sections linked to it are drawn as dashed grey "external" nodes.
- **Transitive reduction** and **Legend** checkboxes; **View**: force-directed (interactive) or layered (Graphviz).
- The graph is rebuilt after every change. Documents with more than 800 statements are not built automatically: untick the kinds you do not need, then press **Build graph**.

### 4. Review and download

- **Graph** tab: drag to pan, scroll to zoom, click a node for its details; in the force-directed view a click also focuses on its prerequisites and/or dependents.
- **Edges** tab: remove an edge with ×, **Restore removed**, or add one with the **Add edge** form (source, target, type, location).
- **Statements** tab: every statement with its kind, label, name and defined terms.
- Downloads: **SVG**, **PNG**, **DOT**, and **TikZ** (`.tex` via `dot2tex`). PNG is rasterised in the browser; on the local server with the `export` extra installed, the layered view's PNG is rendered by Graphviz instead. TikZ is offered only on the local server with the `export` extra.

---

## Example

```latex
\begin{definition}\label{def:ring}
A \emph{ring} is a set with two operations satisfying ...
\end{definition}

\begin{lemma}\label{lem:ring-unit}
\uses{def:ring}
In a ring, if $1=0$ then every element is zero.
\end{lemma}

\begin{proof}
Trivial from the axioms.
\end{proof}

\begin{corollary}\label{cor:trivial-ring}
\uses{def:ring}
If a ring satisfies $1 = 0$, then it is the trivial ring $\{0\}$.
\end{corollary}

\begin{proof}
\uses{lem:ring-unit}
By Lemma~\ref{lem:ring-unit}, if $1 = 0$, then every element equals $0$.
Hence the ring contains only one element, $0$, and is therefore the trivial ring.
\end{proof}
```

In **Manual mode**, this produces:

- **Definition** node (`def:ring`), **Lemma** node (`lem:ring-unit`), **Corollary** node (`cor:trivial-ring`)
- **Dashed edges** from `def:ring` to `lem:ring-unit` and `cor:trivial-ring` (statement-level `\uses{}`)
- **Solid edge** from `lem:ring-unit` to `cor:trivial-ring` (proof-level `\uses{}`)

In **Infer mode**, the same dependencies are discovered automatically through D1 (the `\ref` in the second proof gives `lem:ring-unit` → `cor:trivial-ring`) and D4 (the defined term "ring" gives `def:ring` → `lem:ring-unit` and `def:ring` → `cor:trivial-ring`).

In both modes the dashed edge `def:ring` → `cor:trivial-ring` is removed by the default transitive reduction, because it is implied by `def:ring` → `lem:ring-unit` → `cor:trivial-ring`; it appears only with "Transitive reduction" unticked on the page (`--no-tred` in the CLI).

---

## Notes

- When `\includeonly{...}` is used, only those files are loaded.
- Unticking "Transitive reduction" on the page (`--no-tred` in the CLI) keeps all edges.
- Cycle edges are highlighted in **red** in the graph.
- Zoom/pan gestures:
  - Scroll = zoom
  - Drag = pan
  - "Fit" resets the view; "+" and "−" zoom in and out.
