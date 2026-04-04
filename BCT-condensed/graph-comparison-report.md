# Inferred vs Manual Dependency Graph Comparison — BCT (Basic Category Theory)

This report compares the **inferred** dependency graph (`BCT-knowtex/inferred-graph-BCT.dot`) against the **manual** (gold standard) dependency graph (`BCT_with_uses-knowtex/manual-graph-BCT.dot`) for Leinster's *Basic Category Theory* (condensed version).

The manual graph was constructed using explicit `\uses` annotations in the LaTeX source, while the inferred graph was produced automatically by KnowTeX's heuristic analysis.

> **Note on node naming:** The two graphs use different naming conventions for 8 semantically identical concepts (e.g. `defn:nat-trans` vs `defn:natural-transformation`). This report presents both **raw** and **normalized** results; the normalized analysis maps these names to a common identifier before comparison. The normalization mapping is listed in Section 1.2.

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

Eight concept pairs refer to the same mathematical object under different names:

| Manual Name | Inferred Name |
|-------------|---------------|
| `defn:nat-trans` | `defn:natural-transformation` |
| `defn:comma-cat` | `defn:comma-category` |
| `defn:ess-surj` | `defn:essentially-surjective-on-objects` |
| `defn:full-faithful` | `defn:faithful` |
| `defn:hom-func` | `defn:hom-set` |
| `defn:repr-func` | `defn:representable` |
| `contra-repr-func` | `defn:representation` |
| `defn:contra-hom-func` | `defn:co-rep` |

After normalization, **43 out of 45 nodes** match.

### 1.3 Unmatched Nodes

| Only in manual | Only in inferred |
|----------------|------------------|
| `defn:Hom-func-unified` | `defn:155` |
| `defn:contra-yon-emb` | `defn:156` |

The inferred graph assigns numeric labels (`155`, `156`) to two definitions that the manual graph does not include, and misses `defn:Hom-func-unified` and `defn:contra-yon-emb`.

**Node detection accuracy (normalized): 43/45 = 95.6%**

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
| True Positives (common) | 45 |
| False Negatives (missed) | 16 |
| False Positives (extra) | 20 |
| **Precision** | **0.692** |
| **Recall** | **0.738** |
| **F1 Score** | **0.714** |

Normalization recovers 13 additional edge matches, demonstrating that a significant portion of the raw disagreement stems from naming differences, not structural errors.

### 2.3 Edges Only in Manual (Missed by Inference, Normalized)

| Source | Target | Style |
|--------|--------|-------|
| defn:adjn | cor:adj-triangle | dashed |
| defn:co-rep | defn:representation | dashed |
| defn:co-rep | defn:yon-emb | dashed |
| defn:co-rep | thm:yoneda | dashed |
| defn:comma-category | cor:pre-AFT | dashed |
| defn:faithful | cor:ff-emb | dashed |
| defn:functor | defn:Hom-func-unified | dashed |
| defn:hom-set | defn:contra-yon-emb | dashed |
| defn:hom-set | defn:representable | dashed |
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
| defn:functor | defn:156 | dashed |
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
| thm:yoneda → cor:rep-univ | solid (proof) | dotted (heuristic) |
| thm:yoneda → cor:rep-univ-dual | solid (proof) | dotted (heuristic) |
| thm:yoneda → cor:yoneda-ff | solid (proof) | dotted (heuristic) |

Style agreement on common edges: **42/45 = 93.3%**

All three mismatches involve the Yoneda theorem: the inferred graph marks these as heuristic dependencies, while the manual graph correctly identifies them as arising from proofs.

---

## 3. Path-Based Analysis (Normalized)

A direct edge comparison can be overly strict. If the manual graph has an edge A → B and the inferred graph has a path A → ... → B, the dependency is still captured, just at a different granularity. This section evaluates both graphs from a reachability perspective.

### 3.1 Are Manual Edges Reachable in the Inferred Graph?

For each of the 61 manual edges, we check whether there is **at least a directed path** in the inferred graph:

- **Reachable:** 52 / 61
- **Not reachable:** 9 / 61
- **Path-based recall: 0.852**

Out of the 16 missed direct edges, **7 are recovered through indirect paths**. The 9 truly unreachable edges are:

| Source | Target | Reason |
|--------|--------|--------|
| defn:co-rep | defn:representation | `defn:co-rep` has no outgoing edges to these targets in inferred |
| defn:co-rep | defn:yon-emb | same |
| defn:co-rep | thm:yoneda | same |
| defn:comma-category | cor:pre-AFT | no path in inferred |
| defn:functor | defn:Hom-func-unified | target node missing in inferred |
| defn:hom-set | defn:contra-yon-emb | target node missing in inferred |
| defn:hom-set | defn:representable | no path in inferred |
| defn:isomorphism | defn:essentially-surjective-on-objects | no path in inferred |
| defn:natural-transformation | defn:nat-iso | no path in inferred |

### 3.2 Are Inferred Edges Justified by Manual Paths?

For each of the 65 inferred edges, we check whether there is at least a directed path in the manual graph:

- **Justified:** 51 / 65
- **Truly spurious:** 14 / 65
- **Path-based precision: 0.785**

Out of the 20 extra inferred edges, **6 are transitively justified** by the manual graph (they are shortcut edges that make explicit what is implicit through transitive dependencies):

| Source | Target |
|--------|--------|
| defn:functor | defn:nat-iso |
| defn:functor | defn:representable |
| defn:functor | defn:representation |
| defn:functor | defn:yon-emb |
| defn:natural-transformation | lemma:nat-iso-compts |
| defn:natural-transformation | thm:adj-triangle |

The **14 truly spurious edges** (no path exists in the manual graph) are:

| Source | Target |
|--------|--------|
| defn:faithful | cor:yoneda-ff |
| defn:functor | defn:155 |
| defn:functor | defn:156 |
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
| Common | 157 |
| Only in manual | 26 |
| Only in inferred | 57 |
| **Reachability Precision** | **0.734** |
| **Reachability Recall** | **0.858** |
| **Reachability F1** | **0.791** |

The inferred graph achieves good reachability recall (85.8%), meaning most dependency relationships in the manual graph are also present (directly or transitively) in the inferred graph. However, it introduces 57 extra reachable pairs that do not exist in the manual graph, bringing precision down to 73.4%.

---

## 5. Error Analysis

### 5.1 The `defn:nat-iso` Routing Problem

The most significant structural difference. In the manual graph, the dependency chain is:

```
defn:nat-trans → defn:nat-iso → defn:adjn
defn:nat-trans → defn:nat-iso → defn:eqv
defn:nat-trans → defn:nat-iso → lemma:nat-iso-compts
```

In the inferred graph, `defn:natural-transformation` does **not** connect to `defn:nat-iso`. Instead:
- `defn:functor` connects directly to `defn:nat-iso` (skipping `natural-transformation` as intermediary)
- `defn:nat-in` connects to `defn:adjn` and `defn:eqv` (instead of `defn:nat-iso`)

This rerouting means the inference captures that these concepts are related, but misidentifies the structural mediator.

### 5.2 The `defn:co-rep` Neighborhood

The manual graph has `defn:co-rep` (mapped from `defn:contra-hom-func`) connecting to:
- `defn:representation` (mapped from `contra-repr-func`)
- `defn:yon-emb`
- `thm:yoneda`

The inferred graph has `defn:co-rep` as a leaf node with **no outgoing edges** — it only receives an edge from `defn:functor`. This disconnects the contravariant Hom functor from the Yoneda theorem and representable functor concepts, losing 3 edges and the downstream paths they enable.

### 5.3 Shortcut Edges Through `defn:functor`

The inferred graph adds many direct edges from `defn:functor` that skip intermediate concepts:

```
defn:functor → defn:representable    (should go through defn:hom-set)
defn:functor → defn:representation   (should go through defn:co-rep)
defn:functor → defn:yon-emb          (should go through defn:co-rep)
defn:functor → defn:nat-iso          (should go through defn:natural-transformation)
```

These are transitively justified (the paths exist in the manual graph), but they flatten the dependency hierarchy and obscure the intermediate structure.

### 5.4 Reversed/Misplaced Proof Dependencies

Several edges in the inferred graph connect lemmas/theorems to other lemmas/theorems in directions not present in the manual graph:

- `lemma:init-unique → thm:adj-triangle` (not in manual)
- `lemma:triangle-ids → thm:adj-triangle` (not in manual)
- `lemma:nat-iso-compts → thm:yoneda` (not in manual)
- `thm:adj-triangle → cor:adj-triangle` (not in manual)

In the manual graph, `thm:adj-triangle` depends on `lemma:unit-determines-adjn` and `defn:natural-transformation`, not on `lemma:init-unique` or `lemma:triangle-ids` directly. These inferred edges suggest the heuristic is picking up on textual co-occurrence within proof environments rather than precise dependency.

### 5.5 Yoneda Theorem Style Error

The three `thm:yoneda` output edges are marked as `dotted` (heuristic) in the inferred graph but should be `solid` (proof). The corollaries `cor:rep-univ`, `cor:rep-univ-dual`, and `cor:yoneda-ff` are direct consequences proved using the Yoneda lemma — the inference correctly identifies the edge but misclassifies its type.

---

## 6. Summary

| Aspect | Raw | Normalized | Assessment |
|--------|-----|------------|------------|
| Node detection | 35/45 (78%) | 43/45 (96%) | Good (naming issue) |
| Direct edge Precision | 0.492 | 0.692 | Moderate |
| Direct edge Recall | 0.525 | 0.738 | Moderate |
| Direct edge F1 | 0.508 | 0.714 | Moderate |
| Path-based precision | — | 0.785 | Moderate |
| Path-based recall | — | 0.852 | Good |
| Reachability precision | — | 0.734 | Moderate |
| Reachability recall | — | 0.858 | Good |
| Reachability F1 | — | 0.791 | Good |
| Truly spurious edges | — | 14/65 | Moderate false positive rate |
| Edge style accuracy | — | 42/45 (93%) | Good |

**Strengths:**
- Good node detection after accounting for naming differences (96%)
- Good reachability recall (85.8%): most true dependency paths are captured
- High edge style accuracy (93.3%) on matching edges
- Several extra edges are transitively justified shortcuts, not entirely wrong

**Weaknesses:**
- Significant naming inconsistency (8 out of 45 nodes) inflates raw error rates
- The `defn:co-rep` neighborhood is disconnected, losing the contravariant Hom functor → Yoneda pathway
- `defn:nat-iso` routing is misplaced: connected to `defn:functor` instead of through `defn:natural-transformation`
- 14 truly spurious edges (21.5% of all inferred edges), mostly involving incorrect proof-level dependencies between lemmas/theorems
- Yoneda corollary edges misclassified as heuristic instead of proof-based
- Tendency to flatten the dependency hierarchy by adding shortcut edges through `defn:functor`
