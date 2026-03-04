# KnowTeX: Knowledge Dependency from TeX

**KnowTeX** is a standalone Python GUI tool that analyzes LaTeX projects to construct **knowledge dependency graphs** among mathematical statements and proofs.
It expands your TeX project, parses the document structure, extracts labeled environments, and visualizes how results depend on one another.

Derived from [Patrick Massot's *plastexdepgraph* plugin](https://github.com/PatrickMassot/plastexdepgraph), KnowTeX provides similar functionality **without requiring PlasTeX or Lean blueprints**.

**Artificial Intelligence Disclosure (AID)**

Portions of the KnowTeX project were developed with the assistance of generative AI tools (Claude Opus 4.6). These tools were used to help draft Python code, suggest refactoring patterns, and improve documentation clarity. All generated code was reviewed, tested, and validated by the author, who assumes full responsibility for the final implementation and design decisions.

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
| **H3** | Heuristic | A lemma is linked to the next theorem/proposition within a configurable gap |
| **H4** | Heuristic | **Index-term matching** -- `\index{}` entries are matched across statements using longest-match-first strategy with `\|see{}` alias resolution |

---

## Features

- **LaTeX project expansion**: follows `\input`, `\include`, `\import`, `\subimport`, `\subfile`, and `\includeonly`.
- **Document class detection**: supports both `book`-class (chapters) and `article`-class (sections) documents.
- **Environment recognition**: detects canonical mathematical environments and their aliases (see table below).
- **Defined-term extraction**: extracts terms from `\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`, and `\index{}` entries; uses Snowball stemming for language-aware matching.
- **Cycle detection**: identifies cyclic dependencies using Tarjan's SCC algorithm and highlights them in red.
- **Transitive reduction**: optional simplification of the graph by removing redundant edges.
- **Macro/Micro views**: macro view shows the full graph; micro view focuses on a single section/chapter.
- **Output formats**:
  - **Graphviz DOT** (`.dot`)
  - **TikZ** (`.tex` via `dot2tex`)
  - **Zoomable PNG preview** in the GUI with clickable nodes
- **GUI features**:
  - Chapter/section selection dialog
  - Per-environment inclusion toggles with customizable shapes, border colors, and fill colors
  - Interactive zoom/pan (Ctrl+scroll, left-drag)
  - "Fit" and "100%" view reset buttons

---

## Supported Environments

KnowTeX automatically discovers all `\begin{...}...\end{...}` theorem-like environments in the scanned LaTeX project. Well-known non-theorem environments (e.g. `figure`, `equation`, `align`, `tikzpicture`, etc.) are skipped.

After scanning, the **Environment Configuration** dialog lets users:

- **Include/exclude** each discovered environment from the graph.
- Choose **shape** (`ellipse`, `box`, `diamond`, `doublecircle`), **border color**, and **fill color** per environment.
- In Infer mode, mark which environments are **definition-like** (used by the D4 defined-term matching rule).

Available shape options: `ellipse`, `circle`, `doublecircle`, `box`, `diamond`, `triangle`, `pentagon`, `hexagon`, `octagon`.
Colors can be selected from a preset list or picked via a custom color chooser.

---

## Project Structure

```text
KnowTex/
├── KnowTeX.py              # Entry point
├── knowtex/
│   ├── core/
│   │   ├── constants.py     # Regex patterns, skip sets, GUI constants
│   │   ├── data.py          # Data classes: NodeInfo, ProofInfo, DependencyEdge
│   │   ├── parser.py        # LaTeX parsing and environment extraction
│   │   ├── file_expand.py   # \input/\include/\subfile expansion
│   │   ├── structure.py     # Document class, chapter/section detection
│   │   ├── graph.py         # Graphviz graph construction
│   │   ├── cycles.py        # Tarjan's SCC cycle detection
│   │   └── utils.py         # Utility functions
│   ├── deps/
│   │   ├── manual.py        # Manual mode: \uses{}/\proves{} extraction
│   │   ├── infer.py         # Infer mode: D1-D4, H2-H4 rules
│   │   ├── term_extraction.py  # Stemming and term extraction for D4/H4
│   │   └── index_registry.py   # \index{} registry for H4
│   └── gui/
│       ├── app.py           # Main Tkinter application
│       ├── dialogs.py       # Chapter selection, environment config dialogs
│       └── preview.py       # Zoomable graph preview with clickable nodes
├── test_knowtex.py          # Test suite (pytest)
└── example/                 # Example LaTeX files with and without annotations
```

---

## Installation

**Requirements**

- Python >= 3.8
- Packages:
  ```bash
  pip install pylatexenc pygraphviz dot2tex Pillow PyStemmer
  ```
- [Graphviz](https://graphviz.org/download/) (must be on system `PATH`)

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

### 1. Launch GUI
```bash
python KnowTeX.py
```

### 2. Select your main `.tex` file

- The program expands all `\input` / `\include` / `\subfile` files.
- For book-class documents, optionally select which chapters to include.

### 3. Choose mode and environments

- Select **Manual** or **Infer** mode.
- Check which environment categories to include in the graph.

### 4. Visualize or export

- **Preview**: opens a zoomable graph in the GUI with clickable nodes.
- **Generate DOT + TikZ**: saves `.dot` and `.tex` files with user-configurable names.

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

In **Infer mode**, the same dependencies would be discovered automatically through D1 (proof `\ref`), D2 (statement `\ref`), and D4 (the defined term "ring").

---

## Notes

- When `\includeonly{...}` is used, only those files are loaded.
- The "Nonreduced" option disables transitive reduction (keeps all edges).
- Cycle edges are highlighted in **red** in the graph.
- Zoom/pan gestures:
  - Ctrl + scroll = zoom
  - Left-drag = pan
  - "Fit" and "100%" buttons reset view.
