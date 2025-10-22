# KnowTeX: Knowledge Dependency from TeX

**KnowTeX** is a standalone Python GUI tool that analyzes LaTeX projects to construct **knowledge dependency graphs** among mathematical statements and proofs.  
It expands your TeX project, parses the document structure, extracts labeled environments, and visualizes how results depend on one another via `\uses{...}` and `\proves{...}` annotations.

Derived from [Patrick Massot’s *plastexdepgraph* plugin](https://github.com/PatrickMassot/plastexdepgraph), KnowTeX provides similar functionality **without requiring PlasTeX or Lean blueprints**.

---

## ✨ Features

- Parses a full LaTeX project following:
  - `\input`, `\include`, `\import`, `\subimport`, and `\includeonly`.
- Detects canonical mathematical environments and aliases.
- Tracks logical dependencies between results through:
  - `\uses{...}`, and `\proves{...}`.
- Generates:
  - **Graphviz DOT** and **TikZ** output (`.dot`, `.tex`),
  - Optional **zoomable PNG preview**.
- GUI features:
  - Chapter selection dialog (only scan chosen `\chapter{...}` sections),
  - Environment inclusion toggles,
  - Transitive reduction toggle (for simpler graphs),
  - Interactive zoom/pan of dependency graph.

---

## 🧩 Supported Environments

KnowTeX recognizes the following canonical theorem-like environments (case-insensitive, with aliases such as `defn`, `thm`, `lem`, etc.):


| Canonical | Common Aliases | Shape | Border Color | Fill Color |
|------------|----------------|--------|---------------|-------------|
| **definition** | `definition`, `defn`, `def` | ▢ box | Purple | Lavender |
| **theorem** | `theorem`, `thm`, `th`, `thrm` | ◎ doublecircle | Blue | SkyBlue |
| **lemma** | `lemma`, `lem`, `ilemma`, `alemma` | ◯ ellipse | Blue | SkyBlue |
| **proposition** | `proposition`, `prop`, `propn`, `prp` | ◆ diamond | Blue | SkyBlue |
| **corollary** | `corollary`, `cor`, `corol`, `corl` | ◯ ellipse | Blue | White |
| **construction** | `construction`, `const`, `constn`, `constr` | ◆ diamond | Purple | White |
| **example** | `example`, `examples`, `iexample` | ◯ ellipse | DimGray | White |
| **remark** | `remark`, `remarks` | ◯ ellipse | DimGray | White |

This legend determines how nodes are drawn in the dependency graph.

---

## 🔗 `\uses{...}` and `\proves{...}` Commands

### `\uses{label1,label2,...}`
Declares that the current **statement** (or **proof**) *depends on* or *uses* previously labeled results.

- In a **statement environment** (`theorem`, `lemma`, etc.):  
  Indicates conceptual dependency — the result builds upon these labels.
  Edges from `\uses{...}` in a statement appear as **dashed arrows** in the dependency graph.
- In a **proof environment**:  
  Indicates logical references used *within the proof* of the current result.
  Edges from `\uses{...}` in a proof appear as **solid arrows** in the dependency graph.


### `\proves{label}`
Declares that the current **proof** *establishes* a particular labeled statement.

- Typically appears **inside a proof environment** (e.g. `\begin{proof}...\end{proof}`).
- If omitted, the proof is assumed to prove the **most recent statement** encountered.

---

## 🧮 Example

```latex
\begin{definition}\label{def:ring}
A ring is a set with two operations satisfying ...
\end{definition}

\begin{lemma}\label{lem:ring-unit}
\uses{def:ring}
In a ring, if $1=0$ then every element is zero.
\end{lemma}

\begin{proof}
Trivial from the axioms.
\end{proof}

\begin{corollary}\label{cor:trivial-ring}
\uses{def-ring}
If a ring satisfies $1 = 0$, then it is the trivial ring $\{0\}$.
\end{corollary}

\begin{proof}
\uses{lem:ring-unit}
By Lemma~\ref{lem:ring-unit}, if $1 = 0$, then every element equals $0$.  
Hence the ring contains only one element, $0$, and is therefore the trivial ring.
\end{proof}
```

Produces a graph with:
- a **Definition node** (“def:ring”),
- a **Lemma node** (“lem:ring-unit”),
- a **Corolllary node** ("cor:trivial-ring),
- a **dashed edge** from the definition node to the lemma node.
- a **dashed edge** from the definition node to the corollary node.
- a **solid edge** from the lemma node to the corollary node.

---

## 🧰 Installation

**Requirements**

- Python ≥ 3.8  
- Packages:  
  ```bash
  pip install pylatexenc pygraphviz dot2tex Pillow
  ```
- [Graphviz](https://graphviz.org/download/) (must be on system `PATH`)

**Linux**
```bash
sudo apt install graphviz
```
**macOS**
```bash
brew install graphviz
```
**Windows**
Install Graphviz and add `Graphviz/bin` to your PATH.

---

## 🚀 Usage

### 1. Launch GUI
```bash
python KnowTeX.py
```

### 2. Select your main `.tex` file
- The program expands all `\input` / `\include` files.
- Optionally select which `\chapter{...}` sections to include.

### 3. Choose environments and scan
- Check which categories (theorems, lemmas, etc.) to include.

### 4. Visualize or export
- **Preview**: opens a zoomable graph in the GUI.  
- **Generate DOT + TikZ**: saves `dep_graph.dot` and `dep_graph.tex`, but user can edit the name of the output files.

---

## 🧠 Notes

- When `\includeonly{...}` is used, only those chapters are loaded.
- The “Nonreduced” option disables transitive reduction (keeps all edges).
- Zoom/pan gestures:
  - Ctrl + scroll = zoom
  - Left-drag = pan
  - “Fit” and “100%” buttons reset view.
