# Inferred vs Manual Dependency Graph Comparison

This report compares the **inferred** dependency graph (`group_theory-knowtex/inferred-graph-groups.dot`) against the **manual** (gold standard) dependency graph (`group_theory_with_uses-knowtex/manuel-graph-groups.dot`) for a group theory document.

The manual graph was constructed using explicit `\uses` annotations in the LaTeX source, while the inferred graph was produced automatically by KnowTeX's heuristic analysis.

---

## 1. Node-Level Comparison

Both graphs contain exactly **42 nodes**. There are no missing or extra nodes.

**Node detection accuracy: 100%**

---

## 2. Direct Edge Comparison

| Metric | Value |
|--------|-------|
| Manual edges | 64 |
| Inferred edges | 68 |
| True Positives (common) | 54 |
| False Negatives (missed) | 10 |
| False Positives (extra) | 14 |
| **Precision** | **0.794** |
| **Recall** | **0.844** |
| **F1 Score** | **0.818** |

### 2.1 Edges Only in Manual (Missed by Inference)

| Source | Target | Style |
|--------|--------|-------|
| def:homo | def:kernel-image | dashed |
| def:homo | def:quotient | dashed |
| def:homo | prop:ker-normal | dashed |
| def:homo | thm:cyclic-subgroup-order | solid |
| def:p-subgroup | def:sylow | dashed |
| def:quotient | thm:iso-1 | dashed |
| ex:normal-examples | ex:Z-mod-n | dashed |
| rem:well-defined | thm:iso-1 | solid |
| thm:cyclic-classification | thm:Zm-Zn | dashed |
| thm:lagrange | def:quotient | dashed |

### 2.2 Edges Only in Inferred (Not in Manual)

| Source | Target | Style |
|--------|--------|-------|
| def:coset | def:quotient | dashed |
| def:cyclic-subgroup | thm:Zm-Zn | dashed |
| def:homo | thm:cyclic-classification | dashed |
| def:homo | thm:iso-1 | dashed |
| def:homo | thm:sylow-thm | dashed |
| def:order | def:quotient | dashed |
| def:order | def:sylow | dashed |
| def:quotient | thm:iso-2 | dashed |
| def:quotient | thm:iso-3 | dashed |
| def:subgroup | thm:cyclic-subgroup-order | dashed |
| lem:coset-equality | thm:iso-1 | solid |
| prop:cancellation | thm:cayley | solid |
| thm:cyclic-classification | ex:sylow-15 | dashed |
| thm:lagrange | def:sylow | dashed |

### 2.3 Edge Style Mismatches

Three edges exist in both graphs but with different styles:

| Edge | Manual | Inferred |
|------|--------|----------|
| def:normal -> cor:sylow-normal | dashed (statement) | solid (proof) |
| def:subgroup -> prop:subgroup-test | dashed (statement) | solid (proof) |
| ex:symmetric-group -> thm:cayley | dashed (statement) | dotted (heuristic) |

---

## 3. Path-Based Analysis

A direct edge comparison can be overly strict. If the manual graph has an edge A -> B and the inferred graph has a path A -> ... -> B, the dependency is still captured, just at a different granularity. This section evaluates both graphs from a reachability perspective.

### 3.1 Are Manual Edges Reachable in the Inferred Graph?

For each of the 64 manual edges, we check whether there is **at least a directed path** in the inferred graph:

- **Reachable:** 54 / 64
- **Not reachable:** 10 / 64
- **Path-based recall: 0.844**

The 10 unreachable edges are the same as the missed direct edges listed in Section 2.1. None of them are recovered through indirect paths.

### 3.2 Are Inferred Edges Justified by Manual Paths?

For each of the 68 inferred edges, we check whether there is at least a directed path in the manual graph:

- **Justified:** 66 / 68
- **Truly spurious:** 2 / 68
- **Path-based precision: 0.971**

Out of the 14 extra inferred edges, **12 are transitively justified** by the manual graph. They are not wrong; they are shortcut edges that make explicit what is implicit through transitive dependencies.

The **2 truly spurious edges** (no path exists in the manual graph) are:

| Source | Target |
|--------|--------|
| def:order | def:quotient |
| def:subgroup | thm:cyclic-subgroup-order |

---

## 4. Transitive Closure (Reachability) Comparison

Computing the full transitive closure of both graphs gives the set of all reachable pairs:

| Metric | Value |
|--------|-------|
| Manual reachable pairs | 349 |
| Inferred reachable pairs | 270 |
| Common | 265 |
| **Reachability Precision** | **0.981** |
| **Reachability Recall** | **0.759** |
| **Reachability F1** | **0.856** |

The inferred graph has very high reachability precision (98.1%), meaning it almost never claims a dependency that does not exist. However, its reachability recall is 75.9%: it misses 84 reachable pairs that exist in the manual graph, primarily due to the 10 missing edges and the resulting disconnected subpaths.

---

## 5. Error Analysis

### 5.1 The `def:homo` Problem (4 Missed Edges)

The most significant source of error. In the manual graph, `def:homo` connects to its immediate structural dependencies:

```
def:homo -> def:kernel-image  (dashed)
def:homo -> def:quotient      (dashed)
def:homo -> prop:ker-normal   (dashed)
def:homo -> thm:cyclic-subgroup-order (solid)
```

The inferred graph instead connects `def:homo` directly to more distant targets:

```
def:homo -> thm:cyclic-classification (dashed)
def:homo -> thm:iso-1               (dashed)
def:homo -> thm:sylow-thm           (dashed)
```

This means the inference correctly identifies that `def:homo` is relevant to these theorems, but **skips the intermediate structural concepts** (kernel-image, quotient, ker-normal) that mediate the dependency. As a result, `def:kernel-image` becomes completely **isolated** in the inferred graph (no incoming or outgoing edges).

### 5.2 Isolated Nodes

Several nodes lose all outgoing edges in the inferred graph, becoming "dead ends":

- **def:kernel-image** -- no edges at all (completely disconnected)
- **rem:well-defined** -- no outgoing edges (manual has `rem:well-defined -> thm:iso-1`)
- **ex:normal-examples** -- no outgoing edges (manual has `ex:normal-examples -> ex:Z-mod-n`)
- **def:p-subgroup** -- no outgoing edges (manual has `def:p-subgroup -> def:sylow`)

### 5.3 Dependency Chain Gaps

The manual graph encodes a chain `cor:order-divides -> def:p-subgroup -> def:sylow`. The inferred graph breaks this chain by connecting `def:sylow` to `thm:lagrange` and `def:order` instead, missing `def:p-subgroup` as an intermediary.

Similarly, the chain `thm:cyclic-classification -> thm:Zm-Zn` is replaced by `def:cyclic-subgroup -> thm:Zm-Zn` in the inferred graph.

---

## 6. Summary

| Aspect | Score | Assessment |
|--------|-------|------------|
| Node detection | 100% | Perfect |
| Direct edge F1 | 0.818 | Good |
| Path-based precision | 0.971 | Excellent |
| Path-based recall | 0.844 | Good |
| Reachability precision | 0.981 | Excellent |
| Reachability recall | 0.759 | Moderate |
| Truly spurious edges | 2 / 68 | Very low false positive rate |

**Strengths:**
- Perfect node detection
- Very few truly spurious edges (only 2 out of 68)
- Most extra edges are transitively justified shortcuts
- High reachability precision: the inferred graph rarely claims a false dependency

**Weaknesses:**
- The `def:homo` neighborhood is substantially restructured, missing key intermediate concepts
- Some nodes become isolated (def:kernel-image, rem:well-defined, ex:normal-examples, def:p-subgroup)
- Moderate reachability recall due to missing edges causing downstream path loss
- 3 edges have incorrect style classification (statement vs proof vs heuristic)
