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
13. [GUI Workflow](#13-gui-workflow)

---

## 1. Pipeline Overview

The KnowTeX pipeline has five stages:

```
Load & Expand  →  Structure Detection  →  Parse  →  Edge Extraction  →  Graph Build
```

1. **Load & Expand** (`file_expand.py`): Recursively resolves `\input`, `\include`, `\import`, `\subimport`, `\subfile` into a single expanded string.
2. **Structure Detection** (`structure.py`): Detects document class (book vs article), finds chapter/section ranges.
3. **Parse** (`parser.py`): Walks the expanded LaTeX via pylatexenc AST to extract `NodeInfo` (theorem-like statements) and `ProofInfo` (proof environments).
4. **Edge Extraction**: Either Manual mode (`manual.py`) or Infer mode (`infer.py`) produces a list of `DependencyEdge` objects.
5. **Graph Build** (`graph.py`): Converts nodes and edges into a Graphviz AGraph for rendering.

---

## 2. File Expansion

**Module**: `knowtex/core/file_expand.py`
**Entry point**: `load_and_expand(main_path) -> str`

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

- Returns **False** if it matches `PROOF_ALIAS_RX`: `proof`, `pr`, `pf`, `prf`, `pfof`, `pfoftheorem` (case-insensitive).
- Returns **False** if its lowercase name is in `SKIP_ENVS` (a frozenset of ~60 well-known non-theorem environments such as `document`, `figure`, `equation`, `align`, `tikzpicture`, `enumerate`, etc.).
- Returns **True** for everything else — this means **any custom environment** that isn't a proof or a known structural environment will be discovered as a theorem-like node.

### Node extraction

For each theorem-like environment, a `NodeInfo` is created:

```
NodeInfo(env, label, index, snippet, pos, pos_end, display_name)
```

- **`env`**: The raw environment name (e.g., `"theorem"`, `"defn"`, `"mylemma"`).
- **`label`**: Resolved via the label hierarchy (see Section 5).
- **`index`**: A sequential counter incremented for every theorem-like environment and every proof environment, in document order.
- **`snippet`**: The full LaTeX source from `\begin{...}` to `\end{...}`.
- **`pos`** / **`pos_end`**: Character offsets in the expanded text.
- **`display_name`**: Human-readable short name derived from the label.

### Proof extraction

For each proof-like environment (matching `PROOF_ALIAS_RX`), a `ProofInfo` is created:

```
ProofInfo(index, target_label, snippet, pos, pos_end, target_node_idx)
```

- **`target_label`**: Set if the proof has an explicit target via D3 or `\proves{}` (see below).
- **`target_node_idx`**: Initially set to `last_stmt_idx` (the index of the most recently seen theorem-like node) — this is rule **H1**.

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

**Location**: `"statement"` | **When**: `definition_envs` is non-empty (user has marked some environments as "definition-like" in the GUI).

**Prerequisites**:
- `build_defined_term_registry()` builds a list of `(source_label, source_index, raw_term, stems)` from definition-like environments.
- Terms are extracted from `\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`, and `\index{}` within definition snippets.
- Each term is stemmed using the Snowball English stemmer.
- Only the **first-introducing** node (by document order) is recorded for each term.

**Matching logic**:

For each non-definition node, check if any defined term's stems appear in the node's snippet (also stemmed):

- **Single-word term**: Check if the stem exists in the target node's stem set.
- **Multi-word term**: Check if the stems appear as a **contiguous subsequence** in the target's stem sequence.

**Exclusions**:
- Skip if source and target are the same node.
- Skip if the source appears **after** the target in document order (`src_index >= ni.index`).
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

**When**: `index_registry` is provided (always built when Infer mode is active).

**Prerequisites**: The index registry (`build_index_registry()`) provides `term_to_first_node`: a mapping from normalized index terms to the label of the first node containing them.

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
- **Review table**: Cycle edges are shown with red foreground in the Review dialog.
- **User warning**: A message box warns about detected cycles.

Note: Transitive reduction is applied **including** cycle edges (Graphviz's `tred()` handles this).

---

## 10. Graph Construction and Rendering

**Module**: `knowtex/core/graph.py`
**Entry point**: `build_graph(nodes, edges, env_config, ...) -> AGraph`

### Node rendering

Each included node is added with attributes from `env_config`:

- `shape`: User-configured (from `SHAPE_OPTIONS`)
- `style`: `"filled"`
- `color`: Border color from config
- `fillcolor`: Fill color from config
- `URL` and `tooltip`: Set to the node's label (for clickable image maps)

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

Applied via `AGraph.tred()` (Graphviz's built-in transitive reduction) unless the user checks "Skip transitive reduction". If `tred()` fails, the error is logged and the unreduced graph is used.

---

## 11. Term Extraction and Stemming

**Module**: `knowtex/deps/term_extraction.py`

### Snowball stemmer

Uses PyStemmer (Snowball) English stemmer. All stemming is case-insensitive.

### LaTeX-to-plaintext conversion

`_strip_latex_to_words(snippet) -> list[str]`:

1. Remove inline math (`$...$`), display math (`\[...\]`, `\(...\)`).
2. Remove `\index{}` and `\ntn{}` commands.
3. Remove all LaTeX commands (`\cmd*`).
4. Remove braces and special characters (`{}~^_&$#%`).
5. Split into words, strip punctuation, keep words with length >= 2.
6. Insert sentence boundary markers (`"."`) after sentence-ending punctuation to prevent phrase matching from spanning sentences.

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

For each node's snippet:
1. Find `\index{...}` entries, normalize, resolve aliases.
2. Record first-occurrence mapping: `term → first_node_label`.

Also collects emphasized terms (`\emph`, `\textit`, etc.) from each node and from proof snippets.

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

## 13. GUI Workflow

**Module**: `knowtex/gui/app.py`

### Step-by-step user flow

1. **Select mode**: Manual or Infer (radio buttons). Changing mode resets edges and environment config.

2. **Browse & Load**: User selects a `.tex` file. "Load & Scan" triggers:
   - File expansion (`load_and_expand`)
   - Document class detection
   - Chapter/section range detection
   - Range selection dialog (checkboxes for each chapter/section)
   - The selected ranges are concatenated; unselected ranges are excluded.
   - Parsing (`parse_latex_structure`) on the filtered text.
   - Section assignment for all nodes.

3. **Configure Environments**: Opens `EnvConfigDialog` showing all discovered environments. User sets:
   - Include/exclude checkbox
   - Shape (combobox: `SHAPE_OPTIONS`)
   - Border color (combobox + color picker)
   - Fill color (combobox + color picker)
   - In Infer mode: "Is Defn" checkbox (pre-checked for names matching `DEFN_ENV_RX`)

   On OK, edge extraction runs immediately:
   - **Manual mode**: `extract_manual_edges()`
   - **Infer mode**: `build_index_registry()` + `run_inference()` with `definition_envs` set from "Is Defn" checkboxes.
   - Excluded environments' nodes are filtered out.
   - Cycle detection runs.

4. **Review Edges**: Table view of all edges (source, target, type, location, rule). Cycle edges shown in red. User can:
   - **Delete** selected edges.
   - **Add** new edges manually (with source/target comboboxes and type/location dropdowns).
   - Changes trigger cycle re-detection.

5. **Preview Graph**: Builds the Graphviz graph, applies transitive reduction (unless skipped), renders to PNG at 96 DPI, parses cmapx image map for clickable areas. Displayed on a zoomable/pannable Tkinter canvas.

6. **Export**: Saves to a `{texbase}-knowtex/` directory:
   - `.dot` file (Graphviz source)
   - `.tex` file (TikZ via dot2tex, if available)
   - `.png` file (at 150 DPI)

### Preview interaction

- **Zoom**: Ctrl+scroll (or Cmd+scroll on macOS). Range: 5% to 800%.
- **Pan**: Left-button drag.
- **Click**: Hit-tests against cmapx areas (rect, circle, polygon shapes). On hit, the info panel shows:
  - Section assignment
  - Incoming dependencies grouped by location (proof/statement/inferred/index-based)
  - Outgoing "used by" edges
  - LaTeX snippet (truncated to 1000 chars)
  - A red highlight rectangle around the clicked node.

---

## Appendix A: Environment Name Patterns

| Pattern | Regex | Used by |
|---|---|---|
| Proof aliases | `proof\|pr\|pf\|prf\|pfof\|pfoftheorem` | Parser (classification) |
| Corollary | `corollary\|cor\|corol\|corl` | H2 |
| Theorem/Proposition | `theorem\|thm\|th\|thrm\|proposition\|propn\|prop\|prp` | H2, H3 |
| Lemma | `lemma\|lem\|lm\|lma` | H3 |
| Definition-like (auto-check) | `defn\|definition\|dfn\|def\|constn\|construction\|notation\|ntn\|convention\|conv\|axiom\|ax` | GUI auto-check "Is Defn" |

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

class ProofInfo(NamedTuple):
    index: int                    # Sequential document-order index
    target_label: str | None      # Explicit target
    snippet: str                  # Full LaTeX source
    pos: int                      # Start char position
    pos_end: int                  # End char position
    target_node_idx: int | None   # Parent statement index (H1 default, D3 override)
```

The `index` counter is shared between nodes and proofs — they are interleaved in document order. For example: node(0), node(1), proof(2), node(3), proof(4).
