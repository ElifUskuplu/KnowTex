# KnowTeX Technical Specification

This document is the authoritative technical reference for KnowTeX's internal behavior. It describes how each component works, how edges are produced, and how the pipeline connects together.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [File Expansion](#2-file-expansion)
3. [Document Structure Detection](#3-document-structure-detection)
4. [Parsing: Node and Proof Extraction](#4-parsing-node-and-proof-extraction)
5. [Label Resolution Hierarchy](#5-label-resolution-hierarchy)
6. [Manual Mode](#6-manual-mode)
7. [Infer Mode](#7-infer-mode)
   - [Deterministic Rules (D1-D4)](#71-deterministic-rules-d1-d4)
   - [Heuristic Rules (H1-H4)](#72-heuristic-rules-h1-h4)
8. [Edge Data Model](#8-edge-data-model)
9. [Cycle Detection](#9-cycle-detection)
10. [Graph Construction and Rendering](#10-graph-construction-and-rendering)
11. [Term Extraction and Stemming](#11-term-extraction-and-stemming)
12. [Index Registry](#12-index-registry)
13. [Local Server and Web Page Workflow](#13-local-server-and-web-page-workflow)
14. [Input Formats and the Markdown / Text Front-End](#14-input-formats-and-the-markdown--text-front-end)
15. [Web Build](#15-web-build)
16. [Command Line](#16-command-line)
17. [Web API](#17-web-api)

---

## 1. Pipeline Overview

The KnowTeX pipeline has six stages:

```
Load & Expand  →  Structure Detection  →  Parse  →  Edge Extraction  →  Transitive Reduction  →  Graph Build
```

1. **Load & Expand** (`file_expand.py`): Recursively resolves `\input`, `\include`, `\import`, `\subimport`, `\subfile` into a single expanded string. LaTeX input only; a Markdown or text file is read as it is.
2. **Structure Detection** (`structure.py`): Detects document class (book vs article), finds chapter/section ranges.
3. **Parse** (`formats.py`): `parse_document(text, fmt)` picks the front-end from the given format (or from `detect_format(text)` when none is given; `format_for_path` maps file extensions) and returns `(fmt, nodes, node_by_index, label_to_node, proofs, discovered_envs)`:
   - LaTeX → `parser.py` (`parse_latex_structure`): walks the expanded LaTeX via the pylatexenc AST to extract `NodeInfo` (theorem-like statements) and `ProofInfo` (proof environments).
   - Markdown → `text_parser.py` (`parse_text_structure`), see Section 14. Keyword-only text with no Markdown markup ("Definition 2.1. …", "Proof. …") is read by the same front-end.
4. **Edge Extraction**: Either Manual mode (`manual.py`) or Infer mode (`infer.py`) produces a list of `DependencyEdge` objects. The rules are the same for every input format.
5. **Transitive Reduction** (`cycles.py`, optional, on by default): removes redundant edges, see Section 9.
6. **Graph Build** (`dot.py`): `build_dot` turns nodes and edges into DOT text; the web page draws the layered view from it with viz.js, and the local server renders it with Graphviz for PNG and TikZ export (Section 13).

---

## 2. File Expansion

**Module**: `knowtex/core/file_expand.py`
**Entry points**: `load_and_expand(main_path) -> str` (files on disk: CLI) and `expand_from_files(main_name, files) -> str` (a project held in memory as `{relative path: text}`, rooted at `/`: the web page's **Open LaTeX project folder…**, through `webapi.expand`). Both apply the same rules.

### Process

1. Read the main `.tex` file.
2. Strip LaTeX comments (`%` to end-of-line, respecting `\\%`).
3. Collect `\includeonly{...}` directives from the main file.
4. Recursively expand in this order:
   - `\import{dir}{file}` and `\subimport{dir}{file}`
   - `\input{file}` (braced form) and `\input file` (space form)
   - `\include{file}` — respects `\includeonly` filtering
   - `\subfile{file}` — strips `\documentclass`, `\begin{document}`, `\end{document}` wrappers

### Safety

- **Cycle prevention**: Each absolute file path is visited at most once.
- **Path traversal prevention**: Files outside the project directory are blocked with a comment marker `% [knowtex] blocked path outside project: ...`.
- **Missing files**: Replaced with `% [knowtex] missing file: ...`.
- **Encoding**: Tries UTF-8 first, falls back to Latin-1.

### Extension handling

`ensure_tex_ext(path)`: Appends `.tex` only if the path has no file extension at all.

---

## 3. Document Structure Detection

**Module**: `knowtex/core/structure.py`

### Document class detection

`detect_doc_class(tex) -> "book" | "article"`

Matches `\documentclass[...]{classname}`. Returns `"book"` for: `book`, `report`, `memoir`, `scrbook`, `scrreprt`. Everything else returns `"article"`.

### Range detection

- **Book-class** documents: `find_chapter_ranges(tex)` finds all `\chapter*?[...]?{title}` commands.
- **Article-class** documents: `find_section_ranges(tex)` finds all `\section*?[...]?{title}` commands.

Both return a list of `{"title": str, "start": int, "end": int}` dictionaries, where `start`/`end` are character positions in the expanded text. Each range extends from the command's start to the next command's start (or end of text).

### Section assignment

`assign_sections(nodes, ranges) -> {label: section_title}` assigns each node to the range that contains its `pos`. Nodes outside all ranges are assigned to `"(ungrouped)"`.

---

## 4. Parsing: Node and Proof Extraction

**Module**: `knowtex/core/parser.py`
**Entry point**: `parse_latex_structure(tex) -> (nodes, node_by_index, label_to_node, proofs, discovered_envs)`

### AST Walking

Uses `pylatexenc.latexwalker.LatexWalker` to parse the full expanded text into an AST. Then recursively walks every `LatexEnvironmentNode`.

### Environment classification

An environment is classified by `is_theorem_like(env_name)`:

- Returns **False** if it matches `PROOF_ALIAS_RX`: `proof`, `pr`, `pf`, `prf`, `pfof`, `pfoftheorem`, each optionally starred (`proof*`) (case-insensitive).
- Returns **False** if its lowercase name is in `SKIP_ENVS` (a frozenset of ~115 well-known non-theorem environments such as `document`, `figure`, `figure*`, `table*`, `equation`, `align`, `aligned`, `alignat`, `gathered`, `tikzpicture`, `enumerate`, `algorithm`, etc.).
- Returns **True** for everything else — this means **any custom environment** that isn't a proof or a known structural environment will be discovered as a theorem-like node.

### Node extraction

For each theorem-like environment, a `NodeInfo` is created:

```
NodeInfo(env, label, index, snippet, pos, pos_end, display_name)
```

- **`env`**: The raw environment name (e.g., `"theorem"`, `"defn"`, `"mylemma"`).
- **`label`**: Resolved via the label hierarchy (see Section 5).
- **`index`**: A sequential counter incremented for every theorem-like environment and every proof environment, in document order.
- **`text`**, **`defined_terms`**, **`refs`**: Optional, left `None` by the LaTeX parser (see Appendix D and Section 14).
- **`snippet`**: The full LaTeX source from `\begin{...}` to `\end{...}`.
- **`pos`** / **`pos_end`**: Character offsets in the expanded text.
- **`display_name`**: Human-readable short name derived from the label.

### Proof extraction

For each proof-like environment (matching `PROOF_ALIAS_RX`), a `ProofInfo` is created:

```
ProofInfo(index, target_label, snippet, pos, pos_end, target_node_idx)
```

- **`target_label`**: Set if the proof has an explicit target via D3 or `\proves{}` (see below).
- **`target_node_idx`**: Initially set to `last_stmt_idx` (the index of the most recently seen top-level theorem-like node) — this is rule **H1**. A statement nested inside another statement does not update `last_stmt_idx`, so it never becomes the H1 target of the proof that follows the outer statement.

### Proof target resolution (during parsing)

Two mechanisms can set `target_label` (checked in this order):

1. **D3**: `\begin{proof}[Proof of Theorem \ref{thm:X}]` — the regex `PROOF_OF_REF_RX` extracts the `\ref{...}` label from the optional argument.
2. **`\proves{label}`**: The regex `PROVES_RX` matches `\proves{...}` inside the proof body.

After all nodes and proofs are parsed, a post-processing pass resolves explicit proof targets: if `target_label` is set and exists in `label_to_node`, `target_node_idx` is updated to point to that node's index. This overrides the H1 default.

---

## 5. Label Resolution Hierarchy

When a theorem-like environment is parsed, its label is determined by trying these steps **in order**:

### Step 1: Explicit `\label{}`

Search for `\label{...}` in the snippet. If found and **not inside an inner math environment** (equation, align, gather, etc. — checked via `INNER_LABEL_ENVS`), use that label directly.

If the same explicit label was already used by an earlier node, the later node is renamed `"{label}:{index}"` and a warning is logged.

Note: A `\label{}` inside an inner math environment is **ignored** for node labelling. Since the outer environment has no `\label{}`, the parser falls through to Step 2.

### Step 2: `\emph{}` / `\textit{}` / `\textbf{}` / `\demph{}`

If no explicit label, look for the first emphasized term via `EMPH_RX`. The matched text is cleaned (LaTeX commands removed, braces removed, whitespace collapsed, lowercased) and used as a derived label in the form `"{env}:{cleaned-term}"`, with spaces replaced by hyphens.

### Step 3: `\index{}`

If no emphasized term found, look for the first `\index{...}` entry (skipping `|see` entries). The raw index term is normalized via `normalize_index_term()`: strip modifiers after `|`, use sort key before `@`, preserve hierarchy `!`, lowercase and strip whitespace. Hierarchical terms like `algebra!group` become `"group algebra"` (reversed). Used as `"{env}:{normalized}"`.

### Step 4: Fallback

If nothing else works, the label is `"{env}:{index}"` where `index` is the sequential counter (e.g., `label = "remark:12"`, `display_name = "Remark 12"`).

### Deduplication

In Step 2, all `\emph{}` matches are iterated. If the first match would produce a label that already exists, the parser tries the **next** `\emph{}` match in the same snippet. This way, a more specific term is preferred over appending an index.

If all `\emph{}` candidates collide (or no `\emph{}` is found), the parser falls through to Step 3. If a collision still remains after Steps 2-3, the index is appended as a last resort: `"{env}:{derived}:{index}"`.

### Display name

`_compute_display_name()`: If the label contains `:`, the part after the first `:` is used (with hyphens replaced by spaces). Otherwise, `"{Env} {index}"`.

---

## 6. Manual Mode

**Module**: `knowtex/deps/manual.py`
**Entry point**: `extract_manual_edges(nodes, node_by_index, label_to_node, proofs) -> list[DependencyEdge]`

Manual mode reads **only** explicit `\uses{}` annotations. It produces edges with `edge_type="manual"` and `rule="manual"`.

### Statement-level `\uses{}`

For each node, scan its snippet for `\uses{label1, label2, ...}`. For each comma-separated label that exists in `label_to_node` and is not the node itself, create an edge:

```
DependencyEdge(source=used_label, target=node_label, edge_type="manual", location="statement", rule="manual")
```

### Proof-level `\uses{}`

For each proof, determine its target node via `target_node_idx`. Scan the proof snippet for `\uses{...}`. For each label found:

```
DependencyEdge(source=used_label, target=parent_label, edge_type="manual", location="proof", rule="manual")
```

### Deduplication

A `seen` set of `(source, target)` pairs prevents duplicate edges. Self-edges (`source == target`) are silently dropped.

---

## 7. Infer Mode

**Module**: `knowtex/deps/infer.py`
**Entry point**: `run_inference(nodes, node_by_index, label_to_node, proofs, index_registry=None, definition_envs=None) -> list[DependencyEdge]`

Infer mode applies rules in a fixed order: **D1 → D2 → D4 → H2 → H3 → H4**. Rules D3 and H1 are applied during parsing (see Section 4), not in this function.

All rules share a single `seen` set — if an earlier rule already created an edge `(A, B)`, later rules will not duplicate it.

### 7.1. Deterministic Rules (D1-D4)

Deterministic rules create edges with `edge_type="deterministic"`.

#### D1: Proof cross-references

**Location**: `"proof"` | **When**: For each proof, scan its body (after stripping `\begin{proof}[...]` and `\end{proof}` wrappers) for `\ref{...}`, `\Cref{...}`, `\cref{...}`, and `\eqref{...}`.

**Logic**: For each referenced label that exists in `label_to_node` and is not the proof's own parent statement:

```
Edge: ref_label → parent_label   (type=deterministic, location=proof, rule=D1)
```

**Meaning**: "The proof of `parent_label` uses the result `ref_label`."

#### D2: Statement cross-references

**Location**: `"statement"` | **When**: For each node (theorem-like statement), scan its snippet for `\ref{...}`, `\Cref{...}`, `\cref{...}`, and `\eqref{...}`.

**Logic**: For each referenced label that exists in `label_to_node` and is not the node itself:

```
Edge: ref_label → node_label   (type=deterministic, location=statement, rule=D2)
```

**Meaning**: "The statement of `node_label` explicitly references `ref_label`."

#### D3: Explicit proof target

**Applied during parsing**, not in `run_inference()`.

**When**: A proof environment has an optional argument like `\begin{proof}[Proof of Theorem \ref{thm:X}]`.

**Logic**: The regex `PROOF_OF_REF_RX` extracts the label from the `\ref{...}` inside the optional argument. This overrides the H1 default proof-to-statement association. D3 is checked **before** `\proves{}`.

**Does not produce an edge directly** — it only redirects which statement the proof "belongs to", which affects how D1 edges are attributed.

#### D4: Defined-term matching

**Location**: `"statement"` | **When**: `definition_envs` is non-empty (some environments are marked "definition-like": the **Definition** column on the web page, `definition_envs` in the web API, `--definition-env` in the CLI; by default the names matching `DEFN_ENV_RX`).

**Prerequisites**:
- `build_defined_term_registry()` builds a list of `(source_label, source_index, raw_term, stems)` from definition-like environments.
- Terms are extracted from `\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`, and `\index{}` within definition snippets.
- Each term is stemmed using the Snowball English stemmer (see Section 11).
- Only the **first-introducing** node (by document order) is recorded for each term.

**Matching logic**:

For each node (definitions included), check if any defined term's stems appear in the node's words (also stemmed; see `node_words` in Section 14):

- **Single-word term**: Check if the stem exists in the target node's stem set.
- **Multi-word term**: Check if the stems appear as a **contiguous subsequence** in the target's stem sequence.

**Exclusions**:
- Skip if source and target are the same node.
- Skip if the source appears **after** the target in document order (`src_index >= ni.index`). This check is off when `run_inference` is called with `ordered=False`, i.e. for several Markdown files loaded together, which have no reading order.
- Skip if the target node **itself defines the same term** (exact stem tuple match in the target's own `\emph{}` terms). This prevents a definition from depending on another definition just because they both define the same term.

```
Edge: def_label → node_label   (type=deterministic, location=statement, rule=D4)
```

**Meaning**: "The statement `node_label` uses a term defined in `def_label`."

### 7.2. Heuristic Rules (H1-H4)

Heuristic rules create edges with `edge_type="heuristic"` and `location="inferred"` (except H1, which doesn't create edges).

#### H1: Default proof-to-statement association

**Applied during parsing**, not in `run_inference()`.

**Logic**: Each proof is initially associated with the **most recently encountered** theorem-like statement (by document order). The parser maintains a `last_stmt_idx` variable that is updated whenever a new theorem-like node is created. This is set as the proof's `target_node_idx`.

**Does not produce an edge** — it determines which statement is the "parent" of each proof, which D1 and manual proof-level edges then use as their target.

**Override**: D3 and `\proves{}` can override this default.

#### H2: Corollary → nearest preceding theorem

**When**: A corollary (matching `COROLLARY_RX`: `corollary`, `cor`, `corol`, `corl`) has **no** `\ref` or `\eqref` in its snippet **and** has **no** existing incoming dependency edge (from rules other than D4).

**Logic**: Search backwards through the node list for the nearest preceding theorem or proposition (matching `H2_TARGET_RX`: `theorem`, `thm`, `th`, `thrm`, `proposition`, `propn`, `prop`, `prp`).

```
Edge: theorem_label → corollary_label   (type=heuristic, location=inferred, rule=H2)
```

**Meaning**: "This corollary likely follows from the nearest preceding theorem."

#### H3: Lemma → next theorem/proposition

**When**: A lemma (matching `LEMMA_RX`: `lemma`, `lem`, `lm`, `lma`) has **no** existing edge to the candidate target.

**Logic**: Search forward through the node list for the next theorem or proposition (matching `H2_TARGET_RX`) within a gap of `H3_MAX_GAP = 3` nodes.

```
Edge: lemma_label → theorem_label   (type=heuristic, location=inferred, rule=H3)
```

**Meaning**: "This lemma is likely a stepping stone for the next theorem."

**Suppression**: If D1, D2, or any earlier rule already created an edge `lemma → theorem`, H3 does not add a duplicate.

#### H4: Index-term matching

**When**: `index_registry` is provided. The CLI and the web API build it in Infer mode for **LaTeX input only**; for Markdown H4 does not run.

**Prerequisites**: The index registry (`build_index_registry()`, Section 12) provides `term_to_first_node`: a mapping from normalized `\index{}` terms **and** emphasized terms (`\emph`, `\textit`, `\textbf`, `\demph`) to the label of the first node, in document order, containing them.

**Matching strategy**: Longest-match-first.

1. Collect all terms from `term_to_first_node`, excluding:
   - Terms containing commas.
   - Terms whose first node is in a definition-like environment (these are already handled by D4).
2. For hierarchical terms (`algebra!group`), reverse the segments to get `"group algebra"`.
3. Sort all terms by length (descending) for longest-match-first processing.
4. For each term, stem its words and check every subsequent node (in document order after the introducing node):
   - **Single-word term**: Check if any word in the target node has the same stem **and** has not been "consumed" by a longer term match.
   - **Multi-word term**: Check for contiguous phrase match in the target's stem sequence.

```
Edge: first_label → node_label   (type=heuristic, location=inferred, rule=H4)
```

**Consumed-word tracking**: For single-word matches, once a word in a target node is matched by a term, it is added to a "consumed" set. This prevents the same word occurrence from being matched by multiple shorter terms. Multi-word matches do not use consumed tracking.

---

## 8. Edge Data Model

**Module**: `knowtex/core/data.py`

```python
@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source: str            # Prerequisite node label
    target: str            # Dependent node label
    edge_type: EdgeType    # "deterministic" | "heuristic" | "manual"
    location: Location     # "proof" | "statement" | "inferred"
    rule: RuleName         # "D1" | "D2" | "D3" | "D4" | "H2" | "H3" | "H4" | "manual"
```

### Direction convention

`source → target` means **"target depends on source"**. The arrow in the rendered graph points from prerequisite to dependent, indicating knowledge flow.

### Edge type semantics

| `edge_type` | Meaning |
|---|---|
| `"deterministic"` | Derived from explicit cross-references or term matching (D1, D2, D4) |
| `"heuristic"` | Inferred from structural patterns (H2, H3, H4) |
| `"manual"` | From explicit `\uses{}` annotations |

### Location semantics

| `location` | Meaning | Rendering |
|---|---|---|
| `"proof"` | Edge source was found in a proof body | **Solid** line |
| `"statement"` | Edge source was found in a statement body | **Dashed** line |
| `"inferred"` | Edge was inferred by a heuristic rule | **Dotted** line |

---

## 9. Cycle Detection

**Module**: `knowtex/core/cycles.py`
**Entry point**: `find_cycles(edges) -> set[tuple[str, str]]`

Uses **Tarjan's Strongly Connected Components (SCC) algorithm** with an **iterative (explicit call stack)** implementation to avoid Python's recursion limit.

### Algorithm

1. Build adjacency list from edges.
2. Run iterative Tarjan's SCC to find all strongly connected components with more than one node.
3. For each SCC, collect all edges whose both endpoints are within the SCC.
4. Return the set of `(source, target)` keys for these cycle-participating edges.

### Usage

After edge extraction, `find_cycles()` is called. The returned set is used for:

- **Visual highlighting**: Cycle edges are drawn in **red** in the graph.
- **Edge table**: Cycle edges are marked in the page's Edges tab (`cycle` in the `build` response).
- **Summary**: The page's status line reports the number of edges in cycles (`cycle_count`).

### Transitive reduction

**Entry point**: `transitive_reduction(edges) -> list[DependencyEdge]`

Pure Python, no Graphviz. An edge `u → v` is removed when `v` is reachable from `u` through a path of length ≥ 2 that does not use the edge itself. Reachability is computed on the **condensation** of the graph (one vertex per SCC), where memoized descendant sets are exact; successors of `u` inside `u`'s own SCC are not followed. Edges inside a cycle (the keys returned by `find_cycles`) are **always kept**.

The same function is used by both front-ends: the CLI (on by default, `--no-tred` skips it) and the web page ("Transitive reduction" checkbox, on by default; `tred` in the `build` config). Both run `find_cycles` on the reduced edges; since every cycle edge survives the reduction, this gives the same set of red edges as on the unreduced ones.

---

## 10. Graph Construction and Rendering

**Module**: `knowtex/core/dot.py`
**Entry point**: `build_dot(nodes, edges, env_config, cycle_edges=None, section_assignments=None, filter_sections=None, filter_envs=None, view_mode="macro", micro_section=None, add_legend=True, rankdir=None) -> str`

`dot.build_dot` is the single graph builder; it writes DOT text without pygraphviz. The CLI writes that string to a file, the web page renders it with viz.js (layered view) and offers it as a download, and the local server passes it to pygraphviz or dot2tex for the PNG and TikZ exports (Section 13). The force-directed view is drawn with D3 from the `nodes` and `edges` of the `build` response, not from the DOT. Nodes whose environment is not in `env_config` are omitted.

### Node rendering

Each included node is added with attributes from `env_config`:

- `shape`: User-configured (default `ellipse`; the page offers `ellipse`, `circle`, `doublecircle`, `box`, `diamond`, `triangle`, `pentagon`, `hexagon`, `octagon`)
- `style`: `"filled"`
- `color`: Border color from config
- `fillcolor`: Fill color from config
- `URL` and `tooltip`: Set to the node's label (the page reads `URL` to identify the node clicked in the layered view)

### Edge rendering

Edge line style is determined by `location`:

| Location | Style |
|---|---|
| `"proof"` | `solid` |
| `"statement"` | `dashed` |
| `"inferred"` | `dotted` |

Cycle edges additionally get `color="red"`.

### View modes

- **Macro view**: All nodes from all sections, flat layout (no subgraph clusters).
- **Micro view**: Only nodes from the selected section. Nodes from other sections that are connected to included nodes appear as **ghost nodes** (dashed border, gray fill, ellipse shape).

### Legend

An HTML table node (`__legend__`) is added showing:
- Environment name, shape, and color swatch for each included environment.
- Edge style legend: solid = from proof, dashed = from statement, dotted = heuristic.

### Transitive reduction

Not part of graph building: callers pass the already reduced edge list (Section 9).

---

## 11. Term Extraction and Stemming

**Module**: `knowtex/deps/term_extraction.py`

### Snowball stemmer

Uses the PyStemmer (Snowball) English stemmer; when `PyStemmer` is not installed it falls back to the pure-Python `snowballstemmer` package (same algorithm; this is what the web build uses). All stemming is case-insensitive.

### LaTeX-to-plaintext conversion

`_strip_latex_to_words(snippet) -> list[str]`:

1. Remove display math (`$$...$$`, `\[...\]`, `\(...\)`) and inline math (`$...$`).
2. Remove `\index{}` and `\ntn{}` commands.
3. Remove all LaTeX commands (`\cmd*`).
4. Remove braces and special characters (`{}~^_&$#%`).
5. Split into words (`words_from_plain`), strip the characters `.,;:!?()[]"'` from both ends, keep words with length >= 2, lowercased.
6. After every word that ends in `.`, `,`, `?` or `;`, insert a boundary token `"."` so that phrase matching cannot span a sentence or clause.

### Term extraction from definitions

`extract_defined_terms(node) -> list[(raw_term, stems)]`:

1. Find all `\emph{...}`, `\textit{...}`, `\textbf{...}`, `\demph{...}` in the snippet.
2. Skip terms starting with `\` or `$` (pure LaTeX/math).
3. Clean: remove inner LaTeX commands, remove braces, collapse whitespace.
4. Skip terms shorter than 2 characters.
5. Stem each word; skip terms with any stem shorter than 2 characters.
6. Also extract terms from `\index{...}` entries (excluding `|see` entries), normalized via `normalize_index_term()`.
7. Deduplicate by lowercase term string.

### Emphasized term extraction (for index registry)

`_extract_emph_terms(snippet) -> list[str]`: Similar to above but returns only the cleaned lowercase term strings (not stems).

### Phrase matching

`_contains_phrase(stem_sequence, phrase_stems) -> bool`: Checks if `phrase_stems` appears as a contiguous subsequence within `stem_sequence`. Used for multi-word term matching in both D4 and H4.

---

## 12. Index Registry

**Module**: `knowtex/deps/index_registry.py`
**Entry point**: `build_index_registry(nodes, proofs, tex) -> dict`

### `|see{}` alias resolution

1. Scan the full expanded text for `\index{term|see{canonical}}`.
2. Build an alias map: `alias → canonical`.
3. Resolve transitive chains (with cycle detection).

### Term collection

One pass over the nodes in **document order**. For each node's snippet:
1. Find `\index{...}` entries, skipping cross-reference entries (`\index{x|see{y}}`, which are not a use of `y`); normalize and resolve aliases.
2. Find emphasized terms (`\emph`, `\textit`, `\textbf`, `\demph`) via `_extract_emph_terms`.
3. Record the first-occurrence mapping `term → first_node_label` for both kinds (the first node wins, so an `\emph` in an early node beats an `\index` in a later one).

Proof snippets contribute `\index{}` terms to the hierarchy links only, not to `term_to_first_node`. The registry is built for LaTeX input only.

### Hierarchy links

For hierarchical index terms (containing `!`, e.g., `algebra!group`), build parent-child links. For a term `a!b!c`, the links are: `a → a!b` and `a!b → a!b!c`.

### Return value

```python
{
    "term_to_first_node": {normalized_term: first_node_label, ...},
    "hierarchy_links": [(parent_term, child_term), ...],
}
```

---

## 13. Local Server and Web Page Workflow

**Modules**: `knowtex/serve.py`, `knowtex/webapi.py` (Section 17), `web/template.html` (built into `docs/index.html`, Section 15)

The web page is the only graphical interface. It runs in two ways:

- **Published** (GitHub Pages, or `docs/index.html` opened from any static server): the page loads Pyodide, viz.js and D3 from CDNs and calls `knowtex.webapi` inside the browser.
- **Local server**: `python KnowTeX.py`, `python -m knowtex`, `python -m knowtex serve` or `knowtex-serve` (after `pip install -e .`) start `knowtex/serve.py`, a `ThreadingHTTPServer` on `127.0.0.1:8765` by default, and open the page in the browser. Options: `--port N` (`0` picks a free port), `--no-browser`, `--verbose` (log every request). Any other first argument to `python -m knowtex` runs the command-line tool instead (Section 16).

### Local server endpoints

| Request | Answer |
| ------- | ------ |
| `GET /`, `GET /index.html` | `docs/index.html` with `<script>window.KNOWTEX_LOCAL = {"capabilities": …}</script>` injected after `<head>` |
| `GET /vendor/<name>` | a file of `web/vendor/` (`viz-global.js`, `d3.min.js`), so the page works offline |
| `GET /api/ping` | `{"ok": true, "capabilities": {"png", "svg", "tex"}}` |
| `POST /api/expand`, `/api/structure`, `/api/scan`, `/api/build` | body `{"args": [...]}`; the JSON string returned by the `knowtex.webapi` function of that name |
| `POST /api/export` | body `{"dot", "format": "png" \| "svg" \| "tex"}`; `{"ok", "format", "data"}` with the file base64-encoded, or `{"ok": false, "error"}` |

`/api/export` renders the DOT with pygraphviz (`dot`, 150 DPI) for PNG/SVG and with `dot2tex` (`format="tikz"`, `crop=True`) for TikZ. The capabilities say which of these are available: `png`/`svg` need pygraphviz, `tex` needs dot2tex and pygraphviz (the `export` extra plus Graphviz on the system). When `window.KNOWTEX_LOCAL` is set the page sends every Python call to `/api/<name>` instead of starting Pyodide.

### Step-by-step user flow

1. **Source** (panel "1 · Source text"): paste a document, press a sample button (LaTeX or Markdown), or
   - **Browse file…** (a multi-select file dialog): one `.tex`/`.ltx` or `.md`/`.markdown` file (the extension sets the format; a single `.tex` file that `\input`s others gets a note to use Browse folder…), several `.tex` files of a flat project, or several `.md` files, which are joined in file-name order with blank lines and read as one glossary with no reading order: the build always runs with `ordered: false` (D4 ignores position; see Section 7.1).
   - **Browse folder…** (a `webkitdirectory` input): a LaTeX project. The browser reads the folder; the files whose text contains `\documentclass` are the candidate main files (the shortest path first). If there are several, a **Main file** select appears. `webapi.expand` expands `\input`/`\include`/`\subfile`/`\import` in memory with `file_expand.expand_from_files`; the `% [knowtex] missing file` and `% [knowtex] blocked path` markers are listed as notes under the file name.
   - **Format**: detected automatically, or forced to LaTeX or Markdown for pasted text. **Scan** re-reads pasted text.
2. **Chapters or sections**: for LaTeX, `webapi.structure` returns the chapters (book classes) or sections (article class); a checklist (with *all* / *none*) selects the ones to scan. Changing it scans again (`ranges` in the config).
3. **What to include** (panel "2 · What to include"): `webapi.scan` lists the statement kinds.
   - **Infer** (default) / **Manual** (`\uses{}` annotations only) mode. Switching mode discards the edges added or removed by hand.
   - Environment table: per kind, **Include**, **Definition** (infer mode only; pre-ticked for names matching `DEFN_ENV_RX`), **Shape** (`ellipse`, `circle`, `doublecircle`, `box`, `diamond`, `triangle`, `pentagon`, `hexagon`, `octagon`), **Border** and **Fill** colour.
   - **Scope**: the whole document, or one chapter/section (`micro_section`); statements of other sections linked to it are drawn as dashed grey "ghost" nodes marked *external*.
   - **Transitive reduction** and **Legend** toggles; **View**: force-directed (D3, interactive) or layered (Graphviz through viz.js, with a top → bottom / left → right direction).
   - The graph is built automatically after a scan, and again after every change. A document with more than 800 statements is not built automatically: the user unticks the kinds that are not needed and presses **Build graph**.
4. **Dependency graph** (panel "3 · Dependency graph"), built by `webapi.build`:
   - **Graph** tab: drag to pan, scroll to zoom, *Fit* / + / −. In the force-directed view, hovering a node shows its neighbours and clicking it focuses on its prerequisites and/or dependents up to 1 step, 2 steps or all; in both views a click shows the node's details (kind, label, name, defined terms, the statements it depends on and is used by, snippet).
   - **Edges** tab: one row per edge (rule, source, target, style; cycle edges marked). × removes an edge (`removed`), **Restore removed** brings them back; the **Add edge** form (source, target, type, location) adds one (`added`).
   - **Statements** tab: index, kind, label, name and defined terms of every drawn node.
   - Downloads: **SVG**, **PNG** (the SVG rasterised in the browser at 2×; on the local server with pygraphviz, the layered view is rendered by Graphviz through `/api/export`), **DOT**, and **TikZ** (`.tex` via dot2tex), shown only when the local server reports the `tex` capability.

## Appendix A: Environment Name Patterns

| Pattern | Regex | Used by |
|---|---|---|
| Proof aliases | `proof\|pr\|pf\|prf\|pfof\|pfoftheorem` | Parser (classification) |
| Corollary | `corollary\|cor\|corol\|corl` | H2 |
| Theorem/Proposition | `theorem\|thm\|th\|thrm\|proposition\|propn\|prop\|prp` | H2, H3 |
| Lemma | `lemma\|lem\|lm\|lma` | H3 |
| Definition-like (auto-check) | `defn\|definition\|dfn\|def\|constn\|construction\|notation\|ntn\|convention\|conv\|axiom\|ax` | Default of the **Definition** column on the web page (`is_defn`) and of `definition_envs` / `--definition-env` |

All pattern matches are **case-insensitive** and use `fullmatch` (the entire environment name must match).

## Appendix B: Index Term Normalization

`normalize_index_term(raw) -> str`:

1. Strip everything after the first `|` (modifiers like `textbf`, `see`, `seealso`).
2. Split by `!` (hierarchy separator).
3. For each segment, strip everything after `@` (sort key).
4. Collapse whitespace, lowercase.
5. Rejoin with `!`.

Example: `"cat!func@functor|see{functors}"` → `"cat!func"`

## Appendix C: Rule Execution Order in Infer Mode

```
During parsing:
  H1  (proof → nearest preceding statement, default association)
  D3  (explicit proof target from \begin{proof}[Proof of ... \ref{...}])
  \proves{} override

During run_inference():
  D1  →  D2  →  D4  →  H2  →  H3  →  H4
```

Each rule respects the global `seen` set — an edge `(A, B)` created by D1 will not be duplicated by D2, H3, etc.

## Appendix D: Node Data Structure

```python
class NodeInfo(NamedTuple):
    env: str            # Environment name
    label: str          # Unique label (explicit or auto-generated)
    index: int          # Sequential document-order index
    snippet: str        # Full LaTeX source
    pos: int            # Start char position in expanded text
    pos_end: int        # End char position in expanded text
    display_name: str   # Human-readable short name
    # Filled by the Markdown / text front-end; None for LaTeX nodes
    text: str | None = None                       # Markup-free body text
    defined_terms: tuple[str, ...] | None = None  # Terms this node defines
    refs: tuple[str, ...] | None = None           # Labels this node references

class ProofInfo(NamedTuple):
    index: int                    # Sequential document-order index
    target_label: str | None      # Explicit target
    snippet: str                  # Full LaTeX source
    pos: int                      # Start char position
    pos_end: int                  # End char position
    target_node_idx: int | None   # Parent statement index (H1 default, D3 override)
    text: str | None = None                # Markup-free body text (non-LaTeX)
    refs: tuple[str, ...] | None = None    # Labels referenced in the proof
```

The annotations (`str | None`) and `@dataclass(slots=True)` on `DependencyEdge` require Python 3.10 or later.

The `index` counter is shared between nodes and proofs — they are interleaved in document order. For example: node(0), node(1), proof(2), node(3), proof(4).


---

## 14. Input Formats and the Markdown / Text Front-End

**Modules**: `knowtex/core/formats.py`, `knowtex/core/text_parser.py`

The inference rules (Section 7) do not read LaTeX themselves. They obtain
three things from every node through accessor functions in
`knowtex/deps/term_extraction.py` and `knowtex/deps/infer.py`:

| Accessor | LaTeX node (`text is None`) | Markdown / text node |
| -------- | --------------------------- | -------------------- |
| `node_words(node)` | strip math and commands from `snippet`, tokenize | tokenize `node.text` |
| `defined_term_strings(node)` | `\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`, `\index{}` in `snippet` | `node.defined_terms` |
| `node_refs(node)` / `proof_refs(proof)` | `\ref`, `\Cref`, `\cref`, `\eqref` in `snippet` | `node.refs` / `proof.refs` |

`NodeInfo` and `ProofInfo` (Appendix D) carry the optional fields `text`,
`defined_terms` and `refs` (`ProofInfo`: `text` and `refs`) for this
purpose; the LaTeX parser leaves them `None`.

### Format detection

`formats.detect_format(text)` returns `"latex"` when a `\begin{`,
`\documentclass{`, `\section{`, `\chapter{`, `\label{` or `\ref{` occurs
outside math, otherwise `"markdown"`. `formats.format_for_path`
maps file extensions (`.tex`/`.ltx`, `.md`/`.markdown`) to formats
(default `"latex"`).
`formats.parse_document(text, fmt=None)` dispatches to
`parse_latex_structure` or `parse_text_structure` and returns
`(fmt, nodes, node_by_index, label_to_node, proofs, discovered_envs)`.

### Block scanning (`parse_text_structure`)

Blocks start at the beginning of a line:

- **Keyword header** — an optional marker (`**`, `*`, `_`), a kind word
  (definition/defn/def, theorem/thm, lemma, proposition/prop, corollary/cor,
  remark, example, axiom, notation, convention, conjecture, claim,
  construction, exercise, fact, postulate), an optional number (`2.1`),
  an optional `(name)`, an optional `{#label}`, and a `.`, `:` or dash.
  Outside a Markdown heading a line is a header only if it has
  punctuation after the kind/number, a `(name)`, an `{#id}` or a leading
  emphasis marker; so "Theorem provers …" and a wrapped paragraph line
  such as "Lemma 3 together with …" are not headers.
  The block ends at the first blank line or the next block start.
- **Proof header** — `Proof.`, `Proof:` or `Proof of Theorem 2.1.`
  (the latter sets the explicit target, rule D3). The block ends at an
  end marker at the end of a line (`∎`, `□`, `■`, `QED`, `QED.`,
  `Q.E.D.`, `\qed`, `\blacksquare`) or the next block start.
- **Markdown heading** (`## …`) — with a keyword (`## Theorem 2.1`) it
  opens a statement block that runs to the next heading or block start;
  blank lines do not close it. `## Proof` and `## Proof of Theorem 2.1`
  headings open a proof block in the same way. Without a keyword the
  heading is a section title (or a glossary entry, see below) and closes
  the current block.
- **YAML front matter** with a `title:` line (Markdown only) — a glossary
  entry; the optional `permalink:` becomes an alias slug for link resolution.

*Glossary mode*: when the text contains no keyword blocks, every
keyword-less heading becomes a `definition` entry (the MathGloss layout).
`headings_as_entries=True/False` forces either behaviour.

### Labels

`{#label}` → `kind:number` → `kind:name-slug` → `kind:title-slug` (entries)
→ `kind:first-term-slug` → `kind:index`. Slugs (`slugify`) are lower-case,
`_` and spaces become `-`, other punctuation is dropped; Unicode letters
(`α`, `ö`, …) are kept. Duplicates get the running index appended.

A proof's explicit target (`Proof of Theorem 2.1`, `Proof of Theorem
(Lagrange)`) is first tried as `kind:number` / `kind:name-slug`; if no node
has that label (for example because the statement carries a `{#label}`),
it is resolved through the `(kind, number)` map or the name slug.

### References

- `[text](#label)` — the label itself, or its slug.
- `[text](…/slug)` — the last path segment (case-folded, `.md`/`.html`
  stripped) matched against the slugs of titles, permalinks, names, first
  terms and label suffixes.
- Textual `Theorem 2.1`, `Lemma 3`, `Definition 1.2a` — resolved through
  the `(kind, number)` map of numbered statements.

Links whose target is not a node in the text are ignored.

### Defined terms

- Glossary entry: the title only (bold words in the body are often
  fragments of it and over-match).
- Definition-like keyword block: the parenthesized name, `**bold**`,
  `"quoted"` spans and "called a(n) X" / "known as X" / "termed X" phrases
  (up to four words, stopped by punctuation or `if`, `when`, `such`,
  `that`, `which`, `with`, `where`, `provided`, `of`, `for`, `on`).
- Other kinds: `**bold**` only.

### Text

`strip_markup` removes math (`$…$`, `$$…$$`, `\[…\]`, `\(…\)`), code
spans, images, HTML tags, heading markers, `{#id}`, emphasis markers and
LaTeX commands, and keeps link text. For glossary entries the title is
prepended so that other definitions' terms can match it.

## 15. Web Build

**Modules**: `knowtex/webapi.py`, `knowtex/serve.py`, `web/build.py`,
`web/template.html`, `web/smoke_test.py`, `web/vendor/`, output
`docs/index.html`

`web/build.py` inlines the Python sources listed in `KNOWTEX_FILES` (the
core, including `structure.py` and `file_expand.py`, the `deps` package and
`webapi.py`), seven files of `pylatexenc` (`latexwalker`, `macrospec`,
`_util`, `version`) and the English stemmer of `snowballstemmer` (with a
minimal `__init__.py`), 29 files in all, as a JSON block into the
template. On the published page the browser loads Pyodide from jsdelivr,
writes the bundle into the virtual file system, imports `knowtex.webapi`
and calls `expand`, `structure`, `scan` and `build` (Section 17). Served
by the local server (`python -m knowtex serve`, Section 13), the same page
finds `window.KNOWTEX_LOCAL`, skips Pyodide and sends those calls to
`/api/<name>`; viz.js and D3 then come from `web/vendor/`
(`viz-global.js`, `d3.min.js`) instead of the CDNs.

The page offers the same two formats as the CLI: LaTeX and Markdown.

The DOT is rendered by viz.js (`@viz-js/viz`, Graphviz compiled to
WebAssembly); the force-directed view is drawn with D3. `term_extraction.py`
falls back from `PyStemmer` to `snowballstemmer` automatically, so the same
source runs in CPython and in Pyodide. `web/smoke_test.py` serves `docs/`
(or, with `--local`, the local server) and checks the page in headless
Chromium (Playwright); `--files`, `--project` and `--sweep` exercise the
file dialogs and the controls (see `web/README.md`).
`web/build.py --extract DIR` writes the bundled files into a directory
instead of building the page.

## 16. Command Line

**Module**: `knowtex/cli.py` (`python -m knowtex.cli`, `python -m knowtex PATH`,
or `knowtex` after `pip install`)

```
knowtex PATH [--format {auto,latex,markdown}] [--mode {infer,manual}]
             [--definition-env ENV]... [--no-tred] [--dot FILE] [--json FILE] [--quiet]
```

1. `PATH` is a file or `-` for stdin. With `--format auto` (default) a known
   extension (`FORMAT_BY_SUFFIX`) decides the format; otherwise
   `parse_document` detects it from the content. A `.tex`/`.ltx` file read
   as LaTeX is expanded with `load_and_expand`.
2. `--mode manual` runs `extract_manual_edges`; `--mode infer` (default)
   runs `run_inference` with the definition-like environments given by
   `--definition-env` (repeatable) or, by default, the discovered
   environments matching `DEFN_ENV_RX`. The index registry (H4) is built
   for LaTeX input only.
3. `transitive_reduction` is applied unless `--no-tred` is given; then
   `find_cycles` runs.
4. Unless `--quiet`, a summary (format, statement, proof, edge and cycle
   edge counts) goes to stderr and one line per edge (`rule source ->
   target`, with `(cycle)` for cycle edges) to stdout.
5. `--dot FILE` writes `build_dot` output (all discovered environments,
   default styles). `--json FILE` writes
   `{"format", "nodes": [{"label", "env", "index", "name"}], "edges":
   [{"source", "target", "rule", "type", "location"}]}`.

## 17. Web API

**Module**: `knowtex/webapi.py` (used by the web page, through Pyodide or
through the local server's `/api/<name>` endpoints, Section 13). Every
function takes and returns JSON strings; errors are returned as
`{"ok": false, "error", "trace"}`.

The format is `fmt` or, for `"auto"`/`None`/`""`, `detect_format(text)`;
`parse_document` accepts `"latex"` and `"markdown"` and reports any other
value as an error. The last parse (text, format and selected ranges) is
cached, so `scan` followed by `build` parses once.

- `expand(files_json, main)`: `files_json` is `{relative path: text}` of a
  LaTeX project, `main` the main file's key. Returns `{"ok", "text",
  "notes", "chars"}`; `notes` are the `% [knowtex] …` marker lines
  (missing or blocked files) of the expanded text (`expand_from_files`,
  Section 2).
- `structure(text, fmt="auto")` → `{"ok", "format", "doc_class",
  "range_type", "ranges": [{"index", "title", "start", "end"}]}`.
  `range_type` is `"chapter"` for book classes and `"section"` otherwise;
  Markdown has no ranges.
- `scan(text, fmt="auto", config_json="{}")` → `{"ok", "format",
  "detected", "envs": [{"env", "count", "is_defn"}], "node_count",
  "proof_count", "nodes", "sections"}`. Only `ranges` is read from the
  config. `is_defn` is the `DEFN_ENV_RX` default.
- `build(text, fmt="auto", config_json="{}")` → `{"ok", "format", "mode",
  "edges": [{"source", "target", "type", "location", "rule", "cycle"}],
  "edge_total", "cycle_count", "dot", "nodes", "sections", "h3_gap"}`.
  Config keys and defaults:

  | Key | Default | Meaning |
  | --- | ------- | ------- |
  | `ranges` | whole text | indices of the `structure` ranges to scan; the selected ranges are concatenated |
  | `mode` | `"infer"` | `"manual"` runs `extract_manual_edges` |
  | `include` | all discovered environments | environments to keep (an empty list keeps none) |
  | `definition_envs` | environments matching `DEFN_ENV_RX` | D4 sources |
  | `ordered` | `true` | `false` for several files with no reading order (D4 ignores position) |
  | `tred` | `true` | apply `transitive_reduction` |
  | `micro_section` | none | draw one chapter/section plus the statements of other sections linked to it ("ghost" nodes) |
  | `removed` | `[]` | `[source, target]` pairs deleted in the edge table (removed before reduction) |
  | `added` | `[]` | `[source, target, type, location]` edges added by hand (rule `"manual"`; type defaults to `"manual"` in manual mode and `"deterministic"` otherwise, location to `"proof"`) |
  | `colors` | `{}` | `{env: {"shape", "border", "fill"}}` |
  | `legend` | `true` | add the legend node |
  | `rankdir` | none | Graphviz rank direction (`"TB"`, `"LR"`) |

  The index registry (H4) is built for LaTeX input only. `edges` and
  `nodes` are those of the drawing: with `micro_section`, the section's
  own statements plus the ghosts they touch; `edge_total` counts the edges
  of the whole graph. Nodes are returned as `{"label", "env", "index",
  "name", "terms", "snippet", "section", "ghost"}` (snippet truncated to
  1500 characters; `section` is `"(ungrouped)"` outside every range).
  `sections` lists the sections in order of first statement. `h3_gap` is
  `H3_MAX_GAP`.
