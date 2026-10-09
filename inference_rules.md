# Inference Rules

In **Infer mode** KnowTeX builds the dependency graph from eight rules. This page describes what each rule does and where it stops. (Manual mode does not use these rules; it reads only the author's `\uses{}` annotations.)

An edge `A → B` means "**B depends on A**": the arrow points from the prerequisite to the statement that uses it.

- **Deterministic rules (D1–D4)** follow something written in the text: a reference, or a term introduced in a definition.
- **Heuristic rules (H1–H4)** guess from the order and the kind of the statements. Their edges are drawn **dotted**.

Edges found in a proof are drawn **solid**, edges found in a statement are drawn **dashed**. The rules run in the order D1, D2, D4, H2, H3, H4; D3 and H1 run earlier, while the document is parsed. An edge that an earlier rule already found is not added again, and no statement depends on itself.

## Summary

| Rule | Type | Produces | In short |
| ---- | ---- | -------- | -------- |
| [D1](#d1-references-in-a-proof) | Deterministic | proof edge (solid) | a reference in a proof → the proved statement depends on it |
| [D2](#d2-references-in-a-statement) | Deterministic | statement edge (dashed) | a reference in a statement → the statement depends on it |
| [D3](#d3-explicit-proof-target) | Deterministic | no edge | "Proof of Theorem \ref{…}" fixes which statement a proof belongs to |
| [D4](#d4-defined-terms) | Deterministic | statement edge (dashed) | a term defined in a definition is used in a later statement |
| [H1](#h1-nearest-preceding-statement) | Heuristic | no edge | a proof belongs to the statement just before it |
| [H2](#h2-corollary--preceding-theorem) | Heuristic | dotted edge | a corollary with no reference depends on the preceding theorem |
| [H3](#h3-lemma--next-theorem) | Heuristic | dotted edge | a lemma is used by a theorem that follows it closely |
| [H4](#h4-index-and-emphasized-terms) | Heuristic | dotted edge | an `\index{}` or emphasized term is used in a later statement |

---

## Deterministic rules

### D1: References in a proof

**What it does.** Every reference inside a proof gives an edge from the referenced statement to the statement the proof proves.

- LaTeX: `\ref`, `\cref`, `\Cref`, `\eqref`.
- Markdown: `[text](#label)`, `[text](…/slug)`, and textual references such as "Theorem 2.1" or "Lemma 3".

**Constraints.**
- The reference must point to a statement (theorem-like environment or Markdown block) of the same document. References to sections, equations, figures or other documents are ignored.
- The reference in the proof header (`\begin{proof}[Proof of Theorem \ref{…}]`) is not counted: it is the proof's target (D3), not something the proof uses.
- The edge goes to the statement the proof was attributed to (by D3, `\proves{}` or H1). If that attribution is wrong, so is the edge.

### D2: References in a statement

**What it does.** Every reference inside the text of a statement gives an edge from the referenced statement to this statement. The reference forms are the same as for D1.

**Constraints.** The same as for D1: only references to other statements of the document count, and a statement referring to itself is ignored.

### D3: Explicit proof target

**What it does.** When a proof names the statement it proves, the proof is attached to that statement instead of the one just before it (H1). D3 produces no edge itself; it decides where the D1 edges of the proof go.

- LaTeX: a `\ref`, `\cref` or `\Cref` in the optional argument, `\begin{proof}[Proof of Theorem \ref{thm:main}]`. Only the first reference in the argument is used.
- Markdown: `Proof of Theorem 2.1.` or `## Proof of Theorem 2.1`, also by name: `Proof of Theorem (Lagrange)`.

**Constraints.**
- D3 is checked before `\proves{}`. If the target does not exist in the document, the proof falls back to H1.
- A proof header without a reference ("Proof of the main theorem") is not understood.

### D4: Defined terms

**What it does.** A term introduced in a definition-like statement gives an edge from that definition to every later statement that uses the term.

Definition-like statements are, by default, the environments named `definition`, `defn`, `dfn`, `def`, `notation`, `ntn`, `construction`, `constn`, `convention`, `conv`, `axiom`, `ax` (case-insensitive). The list can be changed: the **Definition** column on the web page, `--definition-env` in the command line.

Where the terms come from:
- LaTeX: `\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}` and `\index{}` inside the definition.
- Markdown: the name in parentheses (`**Definition 2.1 (Ring).**`), `**bold**` text, "quoted" phrases, and phrases after "called a", "known as" or "termed". For a glossary file (no keyword blocks), the entry's title is its only term.

**Constraints.**
- **Order.** Only statements that come *after* the definition are linked. The exception is several Markdown files loaded together: they have no reading order, so every other entry can match.
- **First definition only.** If several definitions introduce the same term, only the first one is a source.
- **Redefinitions.** A statement that itself defines the same term does not get an edge for it.
- **Stemming.** Words are compared after English Snowball stemming, so "rings" matches "ring". The same stemming also makes unrelated words collide ("functional" matches "function"), and non-English text is stemmed as English.
- **Multi-word terms** must appear as consecutive words, and a match cannot cross a sentence or clause boundary (`.`, `,`, `;`, `?`).
- **Math is not read.** Text inside `$…$`, `\[…\]` and similar is removed before matching, as are LaTeX commands. Terms that are pure math (starting with `\` or `$`) and one-letter terms are skipped.
- **Common words over-match.** A term such as "closed" or "group" can link a definition to many statements that only mention the word.
- **Cycle resolution.** If D4 edges close a cycle, the weakest of them are dropped until only cycles formed by the author's own references (D1, D2, D3, `\uses{}`) remain. A D4 edge that contradicts the direction of those references is dropped first; then the edge whose term appears only through its stem, then the edge from a term that matched many statements. The dropped edges are reported. D4 is the only rule whose edges can be dropped this way; `--keep-cycles` in the command line turns it off.

---

## Heuristic rules

### H1: Nearest preceding statement

**What it does.** Every proof belongs, by default, to the statement immediately before it. H1 produces no edge itself; it decides where the D1 edges of the proof go.

**Constraints.**
- D3 and `\proves{label}` override H1.
- A statement nested inside another statement is skipped: a proof after the outer statement belongs to the outer one.
- A proof written far from its statement (for example, in an appendix) is attached to the wrong statement unless D3 or `\proves{}` is used.

### H2: Corollary → preceding theorem

**What it does.** A corollary that cites nothing gets an edge from the nearest theorem or proposition before it.

- Corollaries: environments named `corollary`, `cor`, `corol`, `corl`.
- Theorems and propositions: `theorem`, `thm`, `th`, `thrm`, `proposition`, `propn`, `prop`, `prp`.

**Constraints.**
- H2 runs only if the corollary's statement contains no reference **and** the corollary has no incoming edge from D1 or D2 (for example, from a reference in its proof). A D4 edge does not stop H2.
- The search goes back through the whole document, across sections, with no distance limit. Lemmas and other kinds are passed over.

### H3: Lemma → next theorem

**What it does.** A lemma gets an edge to the first theorem or proposition among the next three statements.

- Lemmas: environments named `lemma`, `lem`, `lm`, `lma`.
- Theorems and propositions: the same names as in H2.

**Constraints.**
- The window is three statements of any kind (definitions and remarks count), set by `H3_MAX_GAP` in `knowtex/core/constants.py`. If there is no theorem or proposition in the window, no edge is added.
- Only the first theorem or proposition in the window is linked.
- H3 adds the edge even if other rules already link the lemma elsewhere; it only skips an edge that already exists.

### H4: Index and emphasized terms

**What it does.** Terms marked with `\index{}` or emphasized (`\emph{}`, `\textit{}`, `\textbf{}`, `\demph{}`) in an ordinary statement give an edge from the first statement that contains the term to every later statement that uses it. It is the counterpart of D4 for terms introduced outside definitions.

**Constraints.**
- **LaTeX only.** H4 does not run on Markdown input.
- Terms whose first statement is definition-like are left to D4.
- Only statements count as sources; an `\index{}` inside a proof does not introduce a term.
- `\index{x|see{y}}` makes `x` an alias of `y`. A hierarchical entry `\index{algebra!group}` is matched as "group algebra". Entries containing a comma are skipped.
- Longer terms are matched first, and a word of a statement that has already matched a single-word term cannot match another one. Multi-word terms must appear as consecutive words.
- The same stemming and the same removal of math apply as in D4.

---

## After the rules

By default a transitive reduction removes an edge `A → C` when `A → B → C` already exists. Edges that are part of a cycle are always kept and drawn in red. On the web page this is the **Transitive reduction** checkbox; `--no-tred` in the command line keeps every edge.

---

## Suggestions welcome

These rules are a first attempt, and we are open to suggestions: a new rule, a change to an existing one, a constraint that is too strict or too loose, or an example where KnowTeX gets a dependency wrong. Please [open an issue](https://github.com/ElifUskuplu/KnowTex/issues) and, if you can, include a short LaTeX or Markdown snippet that shows the case.
