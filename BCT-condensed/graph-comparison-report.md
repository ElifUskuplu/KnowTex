# Inferred vs Manual Dependency Graph Comparison -- BCT (Basic Category Theory)

This report compares the **inferred** dependency graph (`BCT-knowtex/inferred-graph-BCT.dot`) against the **manual** (gold standard) dependency graph (`BCT_with_uses-knowtex/manual-graph-BCT.dot`) for Leinster's *Basic Category Theory* (condensed version).

The manual graph was constructed using explicit `\uses` annotations in the LaTeX source, while the inferred graph was produced automatically by KnowTeX's heuristic analysis.

> **Note on node naming:** The two graphs use different naming conventions for 10 semantically identical concepts (e.g.\ `defn:nat-trans` vs `defn:natural-transformation`). This report presents both **raw** and **normalized** results; the normalized analysis maps these names to a common identifier before comparison. The normalization mapping, verified against the LaTeX source files, is listed in Section 1.2.

---

## 1. Node-Level Comparison

Both graphs contain exactly **45 nodes**.

### 1.1 Raw Overlap

| Metric | Value |
|--------|-------|
| Common nodes (exact name match) | 35 |
| Only in manual | 10 |
| Only in inferred | 10 |

### 1.2 Node Name Mapping

All 10 differing concept pairs refer to the same mathematical object under different names. The mapping below was verified by comparing the definition environments in the LaTeX source files (`rep.tex`, `cfnt.tex`, `adj.tex`) across both modes.

| Manual Name | Inferred Name | Verification Method |
|-------------|---------------|---------------------|
| `defn:hom-func` | `defn:co-rep` | Explicit `\label{}` in both files (same definition: $h^A$) |
| `defn:repr-func` | `defn:representable` | `\demph{representable}` in rep.tex (covariant case) |
| `defn:contra-repr-func` | `defn:representation` | `\demph{representation}` fallback in rep.tex (contravariant case) |
| `defn:Hom-func-unified` | `defn:hom-set` | `\index{hom-set}` in rep.tex (unified $\mathrm{Hom}$ functor) |
| `defn:contra-hom-func` | `defn:156` | Numeric fallback (no `\demph` in definition) |
| `defn:contra-yon-emb` | `defn:155` | Numeric fallback (no `\demph` in definition) |
| `defn:full-faithful` | `defn:faithful` | `\demph{faithful}` in cfnt.tex |
| `defn:nat-trans` | `defn:natural-transformation` | `\demph{natural transformation}` in cfnt.tex |
| `defn:ess-surj` | `defn:essentially-surjective-on-objects` | `\demph{essentially surjective}` in cfnt.tex |
| `defn:comma-cat` | `defn:comma-category` | `\demph{comma category}` in adj.tex |

After normalization, **all 45 nodes** match.

**Node detection accuracy (normalized): 45/45 = 100%**

---

## 2. Direct Edge Comparison

### 2.1 Raw (No Name Normalization)

| Metric | Value |
|--------|-------|
| Manual edges | 61 |
| Inferred edges | 65 |
| True Positives (common) | 32 |
| False Negatives (missed) | 29 |
| False Positives (extra) | 33 |
| **Precision** | **0.492** |
| **Recall** | **0.525** |
| **F1 Score** | **0.508** |

### 2.2 Normalized

After applying the node name mapping from Section 1.2:

| Metric | Value |
|--------|-------|
| Manual edges | 61 |
| Inferred edges | 65 |
| True Positives (common) | 46 |
| False Negatives (missed) | 15 |
| False Positives (extra) | 19 |
| **Precision** | **0.708** |
| **Recall** | **0.754** |
| **F1 Score** | **0.730** |

Normalization recovers 14 additional edge matches, demonstrating that a significant portion of the raw disagreement stems from naming differences, not structural errors.

### 2.3 Edges Only in Manual (Missed by Inference, Normalized)

| Source | Target | Style |
|--------|--------|-------|
| defn:adjn | cor:adj-triangle | dashed |
| defn:co-rep | defn:155 | dashed |
| defn:co-rep | defn:representable | dashed |
| defn:comma-category | cor:pre-AFT | dashed |
| defn:156 | defn:representation | dashed |
| defn:156 | defn:yon-emb | dashed |
| defn:156 | thm:yoneda | dashed |
| defn:faithful | cor:ff-emb | dashed |
| defn:init-term | thm:adj-comma | dashed |
| defn:isomorphism | defn:essentially-surjective-on-objects | dashed |
| defn:isomorphism | lemma:nat-iso-compts | dashed |
| defn:nat-iso | defn:adjn | dashed |
| defn:nat-iso | defn:eqv | dashed |
| defn:natural-transformation | defn:nat-iso | dashed |
| lemma:adj-implies-init | cor:pre-AFT | solid |

### 2.4 Edges Only in Inferred (Not in Manual, Normalized)

| Source | Target | Style |
|--------|--------|-------|
| defn:faithful | cor:yoneda-ff | dashed |
| defn:functor | defn:155 | dashed |
| defn:functor | defn:nat-iso | dashed |
| defn:functor | defn:representable | dashed |
| defn:functor | defn:representation | dashed |
| defn:functor | defn:yon-emb | dashed |
| defn:isomorphism | defn:nat-iso | dashed |
| defn:nat-in | defn:adjn | dashed |
| defn:nat-in | defn:eqv | dashed |
| defn:natural-transformation | lemma:nat-iso-compts | dashed |
| defn:natural-transformation | thm:adj-triangle | dashed |
| defn:representable | cor:rep-univ | dashed |
| defn:representable | cor:rep-univ-dual | dashed |
| lemma:adj-implies-init | thm:adj-comma | dotted |
| lemma:init-unique | thm:adj-triangle | dotted |
| lemma:nat-iso-compts | thm:yoneda | solid |
| lemma:triangle-ids | thm:adj-triangle | dotted |
| propn:eqv-ffeso | cor:ff-emb | dotted |
| thm:adj-triangle | cor:adj-triangle | dotted |

### 2.5 Edge Style Mismatches

Three edges exist in both graphs but with different styles:

| Edge | Manual | Inferred |
|------|--------|----------|
| thm:yoneda -> cor:rep-univ | solid (proof) | dotted (heuristic) |
| thm:yoneda -> cor:rep-univ-dual | solid (proof) | dotted (heuristic) |
| thm:yoneda -> cor:yoneda-ff | solid (proof) | dotted (heuristic) |

Style agreement on common edges: **43/46 = 93.5%**

All three mismatches involve the Yoneda theorem: the inferred graph marks these as heuristic dependencies, while the manual graph correctly identifies them as arising from proofs.

---

## 3. Path-Based Analysis (Normalized)

A direct edge comparison can be overly strict. If the manual graph has an edge A -> B and the inferred graph has a path A -> ... -> B, the dependency is still captured, just at a different granularity. This section evaluates both graphs from a reachability perspective.

### 3.1 Are Manual Edges Reachable in the Inferred Graph?

For each of the 61 manual edges, we check whether there is **at least a directed path** in the inferred graph:

- **Reachable:** 53 / 61
- **Not reachable:** 8 / 61
- **Path-based recall: 0.869**

Out of the 15 missed direct edges, **7 are recovered through indirect paths**. The 8 truly unreachable edges are:

| Source | Target | Reason |
|--------|--------|--------|
| defn:156 | defn:representation | `defn:156` is a leaf node in the inferred graph (no outgoing edges) |
| defn:156 | defn:yon-emb | same |
| defn:156 | thm:yoneda | same |
| defn:co-rep | defn:155 | no path from `defn:co-rep` to `defn:155` in inferred |
| defn:co-rep | defn:representable | no path from `defn:co-rep` to `defn:representable` in inferred |
| defn:comma-category | cor:pre-AFT | no path in inferred |
| defn:isomorphism | defn:essentially-surjective-on-objects | no path in inferred |
| defn:natural-transformation | defn:nat-iso | no path in inferred |

### 3.2 Are Inferred Edges Justified by Manual Paths?

For each of the 65 inferred edges, we check whether there is at least a directed path in the manual graph:

- **Justified:** 53 / 65
- **Truly spurious:** 12 / 65
- **Path-based precision: 0.815**

Out of the 19 extra inferred edges, **7 are transitively justified** by the manual graph (they are shortcut edges that make explicit what is implicit through transitive dependencies):

| Source | Target |
|--------|--------|
| defn:functor | defn:155 |
| defn:functor | defn:nat-iso |
| defn:functor | defn:representable |
| defn:functor | defn:representation |
| defn:functor | defn:yon-emb |
| defn:natural-transformation | lemma:nat-iso-compts |
| defn:natural-transformation | thm:adj-triangle |

The **12 truly spurious edges** (no path exists in the manual graph) are:

| Source | Target |
|--------|--------|
| defn:faithful | cor:yoneda-ff |
| defn:isomorphism | defn:nat-iso |
| defn:nat-in | defn:adjn |
| defn:nat-in | defn:eqv |
| defn:representable | cor:rep-univ |
| defn:representable | cor:rep-univ-dual |
| lemma:adj-implies-init | thm:adj-comma |
| lemma:init-unique | thm:adj-triangle |
| lemma:nat-iso-compts | thm:yoneda |
| lemma:triangle-ids | thm:adj-triangle |
| propn:eqv-ffeso | cor:ff-emb |
| thm:adj-triangle | cor:adj-triangle |

---

## 4. Transitive Closure (Reachability) Comparison

Computing the full transitive closure of both graphs (normalized) gives the set of all reachable pairs:

| Metric | Value |
|--------|-------|
| Manual reachable pairs | 183 |
| Inferred reachable pairs | 214 |
| Common | 161 |
| Only in manual | 22 |
| Only in inferred | 53 |
| **Reachability Precision** | **0.752** |
| **Reachability Recall** | **0.880** |
| **Reachability F1** | **0.811** |

The inferred graph achieves good reachability recall (88.0%), meaning most dependency relationships in the manual graph are also present (directly or transitively) in the inferred graph. However, it introduces 53 extra reachable pairs that do not exist in the manual graph, bringing precision down to 75.2%.

---

## 5. Error Analysis

### 5.1 The `defn:nat-iso` Routing Problem

The most significant structural difference. In the manual graph, the dependency chain is:

```
defn:natural-transformation -> defn:nat-iso -> defn:adjn
defn:natural-transformation -> defn:nat-iso -> defn:eqv
defn:natural-transformation -> defn:nat-iso -> lemma:nat-iso-compts
```

In the inferred graph, `defn:natural-transformation` does **not** connect to `defn:nat-iso`. Instead:
- `defn:functor` connects directly to `defn:nat-iso` (skipping `defn:natural-transformation` as intermediary)
- `defn:nat-in` connects to `defn:adjn` and `defn:eqv` (instead of `defn:nat-iso`)

This rerouting means the inference captures that these concepts are related, but misidentifies the structural mediator.

### 5.2 The `defn:156` (contra-hom-func) Neighborhood

The manual graph has `defn:156` (the contravariant hom functor $h_A$, originally `defn:contra-hom-func`) connecting to:
- `defn:representation` (the contravariant representable functor)
- `defn:yon-emb`
- `thm:yoneda`

The inferred graph has `defn:156` as a leaf node with **no outgoing edges**. It only receives an edge from `defn:functor`. This disconnects the contravariant Hom functor from the Yoneda theorem and representable functor concepts, losing 3 edges and the downstream paths they enable.

This happens because the definition in the LaTeX source has no `\demph{}` term, causing KnowTeX to assign a numeric fallback ID and fail to extract meaningful outgoing dependencies from the definition body.

### 5.3 The `defn:co-rep` (hom-func) Restructuring

The manual graph has `defn:co-rep` (the covariant hom functor $h^A$, originally `defn:hom-func`) connecting to:
- `defn:155` (the contravariant Yoneda embedding)
- `defn:representable` (the covariant representable functor)

The inferred graph skips these intermediate connections: `defn:functor` connects directly to both `defn:155` and `defn:representable`, bypassing `defn:co-rep` as intermediary.

### 5.4 Shortcut Edges Through `defn:functor`

The inferred graph adds direct edges from `defn:functor` that skip intermediate concepts:

```
defn:functor -> defn:representable    (should go through defn:co-rep)
defn:functor -> defn:representation   (should go through defn:156)
defn:functor -> defn:yon-emb          (should go through defn:156)
defn:functor -> defn:155              (should go through defn:co-rep)
defn:functor -> defn:nat-iso          (should go through defn:natural-transformation)
```

These are transitively justified (the paths exist in the manual graph), but they flatten the dependency hierarchy and obscure the intermediate structure.

### 5.5 Reversed/Misplaced Proof Dependencies

Several edges in the inferred graph connect lemmas/theorems to other lemmas/theorems in directions not present in the manual graph:

- `lemma:init-unique -> thm:adj-triangle` (not in manual)
- `lemma:triangle-ids -> thm:adj-triangle` (not in manual)
- `lemma:nat-iso-compts -> thm:yoneda` (not in manual)
- `thm:adj-triangle -> cor:adj-triangle` (not in manual)

In the manual graph, `thm:adj-triangle` depends on `lemma:unit-determines-adjn` and `defn:natural-transformation`, not on `lemma:init-unique` or `lemma:triangle-ids` directly. These inferred edges suggest the heuristic is picking up on textual co-occurrence within proof environments rather than precise dependency.

### 5.6 Yoneda Theorem Style Error

The three `thm:yoneda` output edges are marked as `dotted` (heuristic) in the inferred graph but should be `solid` (proof). The corollaries `cor:rep-univ`, `cor:rep-univ-dual`, and `cor:yoneda-ff` are direct consequences proved using the Yoneda lemma. The inference correctly identifies the edge but misclassifies its type.

---

## 6. Summary

| Aspect | Raw | Normalized | Assessment |
|--------|-----|------------|------------|
| Node detection | 35/45 (78%) | 45/45 (100%) | Perfect (naming issue) |
| Direct edge Precision | 0.492 | 0.708 | Moderate |
| Direct edge Recall | 0.525 | 0.754 | Moderate |
| Direct edge F1 | 0.508 | 0.730 | Moderate |
| Path-based precision | -- | 0.815 | Good |
| Path-based recall | -- | 0.869 | Good |
| Reachability precision | -- | 0.752 | Moderate |
| Reachability recall | -- | 0.880 | Good |
| Reachability F1 | -- | 0.811 | Good |
| Truly spurious edges | -- | 12/65 | Moderate false positive rate |
| Edge style accuracy | -- | 43/46 (93.5%) | Good |

**Strengths:**
- Perfect node detection after accounting for naming differences (100%)
- Good reachability recall (88.0%): most true dependency paths are captured
- High edge style accuracy (93.5%) on matching edges
- 7 extra edges are transitively justified shortcuts, not entirely wrong

**Weaknesses:**
- Significant naming inconsistency (10 out of 45 nodes) inflates raw error rates; two of these receive numeric fallback IDs (`defn:155`, `defn:156`)
- The `defn:156` (contra-hom-func) neighborhood is disconnected, losing the contravariant Hom functor -> Yoneda pathway
- `defn:nat-iso` routing is misplaced: connected to `defn:functor` instead of through `defn:natural-transformation`
- 12 truly spurious edges (18.5% of all inferred edges), mostly involving incorrect proof-level dependencies between lemmas/theorems
- Yoneda corollary edges misclassified as heuristic instead of proof-based
- Tendency to flatten the dependency hierarchy by adding shortcut edges through `defn:functor`
