# KnowTeX: Knowledge Dependency from TeX

**KnowTeX** is a Python tool that reads LaTeX projects or Markdown notes and constructs **knowledge dependency graphs** among mathematical statements and proofs.
It comes as a browser page (run locally or [here](https://elifuskuplu.github.io/KnowTex/)) and a command-line tool; it expands your TeX project, parses the document structure, extracts the statements, and visualizes how results depend on one another.

Derived from [Patrick Massot's *plastexdepgraph* plugin](https://github.com/PatrickMassot/plastexdepgraph), KnowTeX provides similar functionality **without requiring PlasTeX or Lean blueprints**.

**Artificial Intelligence Disclosure (AID)**

KnowTeX was developed with substantial assistance from a generative AI tool (Anthropic's Claude, used through Claude Code). Under the author's direction, the tool wrote significant parts of the Python code, the web page, the tests and the documentation, and proposed the refactorings and performance work recorded in the commit history (commits co-authored by the tool carry a `Co-Authored-By` line). The research questions, the inference rules, the design decisions and the evaluation are the author's; all generated code was reviewed, tested and validated by the author, who assumes full responsibility for the final implementation. 

---

## Two Modes of Operation

KnowTeX offers two complementary modes for constructing dependency graphs:

### Manual Mode

Uses explicit **annotation commands** that authors embed in their LaTeX source:

- `\uses{label1,label2,...}` -- declares that the current statement or proof depends on the listed labels.
- `\proves{label}` -- declares that the current proof establishes a particular labeled statement.

Edges from `\uses{}` in a **statement** appear as **dashed arrows**; edges from `\uses{}` in a **proof** appear as **solid arrows**. If `\proves{}` is omitted, the proof is assumed to prove the most recent statement.

### Infer Mode

Infers dependencies from the document itself, with no annotations: **deterministic rules** (D1–D4) follow what the author wrote, such as `\ref`s and terms introduced in definitions, and **heuristic rules** (H1–H4) guess from the order and kind of the statements, for example linking a corollary to the theorem before it. See [inference_rules.md](inference_rules.md) for what each rule does and its constraints.

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

## Web Page (local or GitHub Pages)

The page `docs/index.html` is KnowTeX's user interface. It runs the same Python code either in the browser through [Pyodide](https://pyodide.org) or on a local Python server, draws the layered graph with [viz.js](https://github.com/mdaines/viz-js) and the default interactive force-directed view with D3 (drag nodes, hover to see a node's neighbours, click a node to keep only its prerequisites and/or dependents up to a chosen depth).

- Local server: `python KnowTeX.py` (or `python -m knowtex serve`) serves the page with native Python and the libraries in `web/vendor/`, so it works offline and large projects run at native speed. With `pip install -e .[export]` (and Graphviz on the system) it also offers Graphviz PNG and TikZ downloads.
- Hosted copy: enable GitHub Pages for this repository (Settings → Pages → *Deploy from a branch*, branch `main`, folder `/docs`); the page is then served at `https://<user>.github.io/KnowTex/`. It loads Pyodide (about 10 MB, cached after the first visit), viz.js and D3 from CDNs. Nothing leaves the browser.
- Rebuild after changing the core: `python web/build.py` (bundles `knowtex/` and the English Snowball stemmer into `docs/index.html`; needs `snowballstemmer` installed, e.g. `pip install -e .[web]`). `python web/smoke_test.py` checks the page in headless Chromium (`--local` for the local server). See `web/README.md`.

## Installation

**Requirements**

- Python >= 3.10
- Packages (declared in `pyproject.toml`):
  ```bash
  pip install -e .            # core: PyStemmer (enough for the CLI and the local server)
  pip install -e .[ast]       # + pylatexenc: the parser's AST engine (KNOWTEX_PARSER=ast), for cross-checks only
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

```bash
python KnowTeX.py        # or: python -m knowtex, python -m knowtex serve, or knowtex-serve after pip install
```

This starts a small local server (`knowtex/serve.py`) on `http://127.0.0.1:8765/` and opens the page in your browser. Options: `--port N` (`0` picks a free port), `--no-browser`, `--verbose`. Stop it with Ctrl-C. The same page works without installing anything on GitHub Pages (see [Web Page](#web-page-local-or-github-pages)).

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
