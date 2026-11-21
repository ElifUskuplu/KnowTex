# KnowTeX: Knowledge Dependency from TeX

**KnowTeX** reads LaTeX projects or Markdown notes and builds the **dependency graph** of their definitions, theorems and proofs. It comes as a browser page ([hosted copy](https://elifuskuplu.github.io/KnowTex/), or run locally) and as a command-line tool.

It is derived from [Patrick Massot's *plastexdepgraph* plugin](https://github.com/PatrickMassot/plastexdepgraph) and produces similar graphs **without PlasTeX or a Lean blueprint**.

**Artificial Intelligence Disclosure.** KnowTeX was developed with substantial assistance from a generative AI tool (Anthropic's Claude, through Claude Code). Under the first author's direction it wrote significant parts of the Python code, the web page, the tests, the benchmark scripts and the documentation; commits co-authored by the tool carry a `Co-Authored-By` line. The research questions, the inference rules, the design decisions, the evaluation design and the manual classification of edges are the authors' own. All generated code was reviewed, tested and validated by the authors, who assume full responsibility for the final implementation.

## Two modes

**Manual mode** reads the annotation commands of Lean Blueprint:

- `\uses{label1,label2,...}` declares that the current statement or proof depends on the listed labels.
- `\proves{label}` declares which statement a proof establishes; without it, the proof belongs to the most recent statement.

A `\uses{}` in a statement gives a **dashed** edge, one in a proof a **solid** edge.

**Infer mode** needs no annotations. Deterministic rules (D1–D4) follow what the author wrote, such as `\ref`s and the terms introduced in definitions; heuristic rules (H1–H4) guess from the order and kind of the statements, for example linking a corollary to the theorem before it. [inference_rules.md](inference_rules.md) describes every rule.

## Input formats

The rules are the same for both formats; only the front-end that finds statements, defined terms and references differs.

| Format | Statements | Defined terms (D4) | References (D1/D2) |
| ------ | ---------- | ------------------ | ------------------ |
| **LaTeX** (`.tex`, projects with `\input`) | theorem-like environments | `\emph{}`, `\textit{}`, `\textbf{}`, `\index{}` | `\ref`, `\Cref`, `\cref`, `\eqref` |
| **Markdown** (`.md`) | `## Theorem 2.1 (Name)` headings or `**Definition 2.1.**` paragraphs; `Proof.` … `∎` | `**bold**`, the parenthesized name, "quoted" and "called a …" phrases | `[text](#label)`, `[text](…/slug)`, textual "Theorem 2.1" |

A Markdown file or folder with no keyword blocks is read as a glossary: every heading (or YAML `title:`) is a definition whose title is the defined term. Labels come from `\label{}` / `{#label}`, otherwise from the number (`theorem:2.1`), the name, the first defined term, or a running index.

## Installation

Python 3.10 or later.

```bash
pip install -e .            # core (PyStemmer); enough for the CLI and the local server
pip install -e .[export]    # + pygraphviz, dot2tex: PNG and TikZ downloads from the local server (needs Graphviz)
pip install -e .[web]       # + snowballstemmer: rebuild docs/index.html
pip install -e .[test]      # + pytest, playwright, pylatexenc: tests and the web smoke test
pip install -e .[ast]       # + pylatexenc: the parser's AST engine (KNOWTEX_PARSER=ast), for cross-checks
```

This installs the commands `knowtex` (CLI) and `knowtex-serve` (local server). [Graphviz](https://graphviz.org/download/) is needed on the system only for the `export` extra.

## Usage

### Web page

```bash
python -m knowtex            # or: python KnowTeX.py, or knowtex-serve
```

This starts a local server on `http://127.0.0.1:8765/` and opens the page in the browser (`--port N`, `--no-browser`, `--verbose`; Ctrl-C stops it). The page loads pasted text, files or a LaTeX project folder, scans the chosen chapters, builds the graph in infer or manual mode and draws it: a force-directed view with D3 (drag nodes, hover for a node's neighbours, click a node to keep only its prerequisites and dependents up to a chosen depth) and a layered view with viz.js.

The [hosted copy](https://elifuskuplu.github.io/KnowTex/) runs the same Python code in the browser through Pyodide; nothing leaves the browser. See [web/README.md](web/README.md) for how the page is built and tested.

### Command line

```bash
python -m knowtex.cli notes.md                    # print inferred edges
python -m knowtex.cli main.tex --dot graph.dot    # write Graphviz DOT
python -m knowtex.cli notes.md --json out.json    # nodes and edges as JSON
python -m knowtex.cli main.tex --mode manual      # \uses{} annotations only
python -m knowtex.cli glossary/                   # a folder of Markdown files, as one glossary
python -m knowtex.cli main.tex --include-env defn --include-env thm --include-env lemma
python -m knowtex.cli main.tex --config run.json  # the options of a page run, as JSON
cat notes.md | python -m knowtex.cli -            # read from stdin
```

After `pip install -e .` the same command is `knowtex`; `python -m knowtex notes.md` also runs it. The options that change the edges (`--mode`, `--include-env`, `--definition-env`, `--unordered`, `--disable-rule`, `--keep-cycles`, `--no-tred`) are the keys the web page sends, and `--config FILE` reads them from JSON, so any graph built on the page can be rebuilt from the terminal. Both go through `knowtex/pipeline.py`, which scripts can import directly (`run_pipeline(text, fmt, PipelineConfig)`).

## Datasets and regression check

The repository includes several datasets used to test KnowTeX, each with its source and, in a `-knowtex/` folder, the graph KnowTeX builds from it (DOT and PNG):

- `example/`: group theory lecture notes, with and without `\uses{}`.
- `BCT-condensed/`: three chapters of Leinster's *Basic Category Theory*, both versions.
- `Polynomial-Freiman-Ruzsa/`: the PFR blueprint, with and without `\uses{}`.
- `chicago_notes/`: the MathGloss Chicago glossary, downloaded by its benchmark script ([chicago_notes/README.md](chicago_notes/README.md)).

`tests/datasets.py` records how each graph is built; `tests/regression.py` rebuilds them and compares the edges with the stored graphs, exiting with status 1 on any difference. Run it after changing a rule; `pytest` includes the same check.

```bash
python tests/regression.py            # rebuild all and compare with the stored graphs
python tests/regression.py --write    # rewrite the stored graphs after an intended change
python chicago_notes/chicago_benchmark.py
```

`knowtex/evaluation.py` scores a run against a dataset's gold standard (precision, recall, F1, path-based variants, edge-style agreement).

## Limitations

KnowTeX reads the source as written: references hidden behind custom wrapper macros are not seen, and statement kinds are recognized from common environment names. The full list, and how to add a rule, is at the end of [inference_rules.md](inference_rules.md#limitations-of-the-parser).
