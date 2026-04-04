# Three-Way Dependency Graph Comparison — PFR (Polynomial Freiman-Ruzsa)

This report compares three dependency graphs for the PFR Blueprint project (Terence Tao et al.):

1. **Manual (KnowTeX)**: produced by KnowTeX in manual mode, using explicit `\uses` annotations in the LaTeX source (`with_uses/print-knowtex/pfr_manual_graph.dot`). The original LaTeX source files provided by the Blueprint authors were used directly without any modification or intervention.
2. **Inferred (KnowTeX)**: produced by KnowTeX in infer mode, using heuristic analysis only (`without_uses/print-knowtex/pfr_infer_graph.dot`). The only modification made to the original LaTeX source was removing all `\uses` commands; no other changes were applied.
3. **Blueprint (Lean)**: the dependency graph from the official Lean Blueprint website, extracted from the SVG embedded in the dependency graph HTML page (`Dependency graph.html`).

The Blueprint graph represents the formalized mathematical structure as curated by the project authors and is treated as the primary reference. The Manual graph uses the same LaTeX source with `\uses` annotations that mirror the Blueprint's dependency structure. The Inferred graph attempts to recover dependencies automatically from the LaTeX text alone.

**Note on dual labels:** Some LaTeX environments carry two `\label{}` commands (e.g., `\label{rhominus-nonneg}\label{rhoMinus_nonneg}`). The Blueprint uses one label and KnowTeX uses the other. These aliases are resolved throughout this comparison so that both names map to the same node:
- `rhoMinus_nonneg` (Blueprint) = `rhominus-nonneg` (KnowTeX)
- `rho_of_uniform` (Blueprint) = `rho-init` (KnowTeX)

---

## 1. Graph Sizes

| Graph | Nodes | Edges |
|-------|-------|-------|
| Manual (KnowTeX `\uses`) | 218 | 403 |
| Inferred (KnowTeX heuristic) | 218 | 343 |
| Blueprint (Lean) | 218 | 403 |

After alias resolution, all three graphs have the same 218 nodes. The Manual and Blueprint graphs also share the same edge count (403), while the Inferred graph has fewer edges (343).

Edge style breakdown:

| Graph | Solid | Dashed | Dotted |
|-------|-------|--------|--------|
| Blueprint | 341 | 62 | 0 |
| Manual | 340 | 63 | 0 |
| Inferred | 334 | 5 | 4 |

---

## 2. Node-Level Comparison

After alias resolution, all three graphs share the exact same 218 nodes. There are no nodes unique to any single graph or pair of graphs.

---

## 3. Pairwise Edge Comparisons

Since all three graphs share the same 218 nodes, all edge comparisons use the full node set.

### 3.1 Blueprint vs Manual

| Metric | Value |
|--------|-------|
| Blueprint edges | 403 |
| Manual edges | 403 |
| True Positives | 402 |
| False Negatives (missed by Manual) | 1 |
| False Positives (extra in Manual) | 1 |
| **Precision** | **0.998** |
| **Recall** | **0.998** |
| **F1 Score** | **0.998** |

The Manual graph recovers 402 out of 403 Blueprint edges — near-perfect agreement. The single missed edge is `eta-def-multi -> k-vanish` (solid). The single extra Manual edge is `eta-def-multi -> tau-def-multi` (dashed) — a statement-level dependency from `\uses` annotation that the Blueprint maps differently.

**Edge style match rate: 100%** — all 402 matching edges have identical styles (solid vs dashed).

**Path-based recall: 1.000** — every Blueprint edge is reachable (directly or via path) in the Manual graph.

**Path-based precision: 0.998** — the 1 extra Manual edge is not justified by Blueprint paths.

### 3.2 Blueprint vs Inferred

| Metric | Value |
|--------|-------|
| Blueprint edges | 403 |
| Inferred edges | 343 |
| True Positives | 308 |
| False Negatives (missed by Inferred) | 95 |
| False Positives (extra in Inferred) | 35 |
| **Precision** | **0.898** |
| **Recall** | **0.764** |
| **F1 Score** | **0.826** |

The Inferred graph misses 95 Blueprint edges (23.6% miss rate) and adds 35 edges not in the Blueprint.

**Edge style mismatches: 11 / 308 (96.4% match rate)**

| Edge | Blueprint | Inferred |
|------|-----------|----------|
| ruz-dist-def -> ruzsa-symm | dashed | solid |
| ruz-dist-def -> ruzsa-diff | dashed | solid |
| ruz-dist-def -> ruz-copy | dashed | solid |
| ruz-dist-def -> ruz-indep | dashed | solid |
| ruz-dist-def -> ruzsa-growth | dashed | solid |
| entropy-def -> copy-ent | dashed | solid |
| conditional-entropy-def -> relabeled-entropy-cond | dashed | solid |
| conditional-mutual-def -> conditional-nonneg | dashed | solid |
| cond-multidist-def -> cond-multidist-nonneg | dashed | solid |
| multidist-def -> multidist-chain-rule | dashed | solid |
| conditional-nonneg -> multidist-chain-rule-iter | solid | dashed |

10 of 11 mismatches follow the same pattern: the Blueprint marks definition-to-lemma edges as **dashed** (statement-level), but the Inferred graph marks them as **solid** (proof-level). Verification in the LaTeX source confirms that the Inferred graph is correct in all 11 cases:

- **Edges 1–10 (Blueprint=dashed, Inferred=solid):** The `\ref` to the source definition appears exclusively in the **proof** of the target lemma, not in its statement. Examples: `ruzsa-symm`'s proof references `\Cref{ruz-dist-def}`; `copy-ent`'s proof references `\Cref{entropy-def}`. Since the reference is in the proof, `solid` is the correct classification.
- **Edge 11 (Blueprint=solid, Inferred=dashed):** `conditional-nonneg -> multidist-chain-rule-iter`. The `\Cref{conditional-nonneg}` appears inside the lemma statement in `torsion.tex`, not in the proof. So `dashed` is correct.

The mismatches reflect a convention difference: the Blueprint classifies edges by **structural role** (definition edges are always dashed), while KnowTeX classifies by **textual location** of the reference (proof vs statement). Both conventions are internally consistent.

**Path-based recall: 0.814** — about 81% of Blueprint edges are reachable via some path in the Inferred graph. The remaining 19% are structurally disconnected.

**Path-based precision: 0.921** — 27 of the 35 extra Inferred edges are truly spurious (no path exists in the Blueprint).

### 3.3 Manual vs Inferred

| Metric | Value |
|--------|-------|
| Manual edges | 403 |
| Inferred edges | 343 |
| True Positives | 307 |
| False Negatives (missed by Inferred) | 96 |
| False Positives (extra in Inferred) | 36 |
| **Precision** | **0.895** |
| **Recall** | **0.762** |
| **F1 Score** | **0.823** |

The Inferred graph misses 96 Manual edges and adds 36 extras. The miss rate (23.8%) is consistent with the Blueprint comparison, confirming that the same structural gaps are present.

**Edge style mismatches: 11 / 307 (96.4% match rate)** — identical set of 11 mismatches as in the Blueprint comparison.

**Path-based recall: 0.811** — 81% of Manual edges are reachable via paths in the Inferred graph.

**Path-based precision: 0.921** — 27 of 36 extra Inferred edges are truly spurious (no path in Manual).

---

## 4. Transitive Closure (Reachability) Comparison

| Metric | Bp vs Man | Bp vs Inf | Man vs Inf |
|--------|-----------|-----------|------------|
| Reference reachable pairs | 4,860 | 4,860 | 4,869 |
| Compared reachable pairs | 4,869 | 4,527 | 4,527 |
| Common | 4,860 | 3,994 | 3,994 |
| **Reachability Precision** | **0.998** | **0.882** | **0.882** |
| **Reachability Recall** | **1.000** | **0.822** | **0.820** |
| **Reachability F1** | **0.999** | **0.851** | **0.850** |

The Manual graph achieves perfect reachability recall against the Blueprint — every dependency chain in the Blueprint is preserved. The Inferred graph has moderate reachability (82% recall), meaning about 1 in 5 Blueprint dependency paths has no equivalent in the Inferred graph.

---

## 5. Error Analysis

### 5.1 Systematic Definition-Level Dependency Loss (95 Missed Edges)

The dominant failure mode of the Inferred graph is **missing definition-to-definition and definition-to-lemma edges**. Of the 95 missed Blueprint edges, approximately 49 are dashed (statement-level) and 46 are solid (proof-level).

The dashed (statement-level) misses include:

```
entropy-def -> relabeled-entropy          (dashed, missed)
entropy-def -> conditional-entropy-def    (dashed, missed)
entropy-def -> information-def            (dashed, missed)
entropy-def -> ruz-dist-def              (dashed, missed)
entropy-def -> jensen-bound              (dashed, missed)
entropy-def -> uniform-entropy           (dashed, missed)
entropy-def -> uniform-entropy-II        (dashed, missed)
entropy-def -> bound-conc               (dashed, missed)
ruz-dist-def -> tau-def                   (dashed, missed)
ruz-dist-def -> dist-zero                 (dashed, missed)
multidist-def -> tau-def-multi            (dashed, missed)
multidist-def -> cond-multidist-def      (dashed, missed)
multidist-def -> multidist-nonneg        (dashed, missed)
multidist-def -> multidist-perm          (dashed, missed)
rho-def -> rho-cts                        (dashed, missed)
rho-def -> rho-init                       (dashed, missed)
rho-def -> rho-invariant                  (dashed, missed)
rho-def -> rho-subgroup                   (dashed, missed)
rhominus-def -> rhominus-nonneg          (dashed, missed)
```

These are statement-level dependencies declared via `\uses{}` that the Inferred mode cannot recover because the definitions do not explicitly `\ref` each other in the LaTeX text. The `\uses` command is the only signal, and without it, these structural relationships are invisible to heuristic analysis.

### 5.2 Missing Proof-Level Dependencies

Several proof-level (solid) edges are also missed. Key clusters include:

**kl-div subgraph disconnection** — The Inferred graph entirely misses the `kl-div` node's outgoing edges:

```
kl-div -> kl-div-convex      (solid, missed)
kl-div -> kl-div-copy        (solid, missed)
kl-div -> kl-div-inj         (solid, missed)
kl-div -> Gibbs              (dashed, missed)
kl-div -> ckl-div            (dashed, missed)
```

**Rho-functional subgraph disconnection** — The `rho`/`phi`-minimizer subgraph is largely missing:

```
phi-min-def -> phi-first-estimate     (solid, missed)
phi-min-def -> phi-second-estimate    (solid, missed)
phi-min-exist -> pfr-rho              (solid, missed)
rho-def -> rho-cts                    (dashed, missed)
rho-def -> rho-invariant              (dashed, missed)
rho-cond-def -> rho-cond-relabeled    (solid, missed)
rho-cond-def -> rho-cond-invariant    (solid, missed)
rho-cts -> phi-min-exist              (solid, missed)
```

**Hub nodes losing incoming edges** — Multiple edges targeting `pfr_aux-improv` and `pfr_aux_torsion` are missed:

```
bound-conc -> pfr_aux-improv          (solid, missed)
bound-conc -> pfr_aux_torsion         (solid, missed)
jensen-bound -> pfr_aux-improv        (solid, missed)
jensen-bound -> pfr_aux_torsion       (solid, missed)
ruz-cov -> pfr_aux-improv             (solid, missed)
ruz-cov -> pfr_aux_torsion            (solid, missed)
unif-exist -> pfr_aux-improv          (solid, missed)
unif-exist -> pfr_aux_torsion         (solid, missed)
uniform-entropy-II -> pfr_aux-improv  (solid, missed)
uniform-entropy-II -> pfr_aux_torsion (solid, missed)
```

**Cross-chapter dependencies** — Several edges connecting results across distant chapters are missed:

```
concave -> converse-log-sum           (solid, missed)
concave -> mutual-nonneg              (solid, missed)
submodularity -> entropic-bsg         (solid, missed)
more-random -> Zero-sum               (solid, missed)
sym-group-def -> zero-large           (solid, missed)
zero-large -> sym-zero                (solid, missed)
sym-zero -> pfr-rho                   (solid, missed)
```

### 5.3 Spurious Edges in Inferred Graph (35 extra edges)

The 35 extra Inferred edges fall into several categories:

**Heuristic shortcuts** — the Inferred graph connects distant results that share textual references but have no actual dependency:

- `ruzsa-triangle -> pfr-rho`, `ruzsa-nonneg -> pfr-rho` — incorrect direct links to the rho-PFR result.
- `pfr-9-aux' -> pfr-9`, `pfr-9-aux' -> hom-pfr`, `pfr-9-aux' -> approx-hom-pfr` — misplaced edges from an auxiliary result.
- `pfr -> pfr-9`, `pfr -> pfr-improv`, `pfr -> pfr-torsion`, `pfr -> weak-pfr-int` — the inference links the main PFR theorem to its variants, but these are siblings, not parent-child.
- `pfr_aux -> pfr-9-aux`, `pfr_aux -> pfr_aux-improv`, `pfr_aux -> pfr_aux_torsion` — similar sibling misidentification.

**Dotted (heuristic) edges** — 4 edges the Inferred graph itself marks as uncertain:

- `Zero-sum -> prop:52` (dotted)
- `lem:100pc-self -> fibring-ident` (dotted)
- `multidist-ruzsa-III -> multi-zero` (dotted)
- `multidist-ruzsa-IV -> multi-zero` (dotted)

**Incorrect proof attribution**:

- `tau-def -> distance-lower` — tau definition is not a direct proof dependency of distance-lower.
- `tau-min -> tau-min-exist-multi` — tau-min is not a direct dependency of the multi version.
- `copy-ent -> multidist-copy` — incorrect direct edge.
- `eta-def -> de-prop` — eta definition is not a direct dependency of de-prop.
- `concave -> log-sum`, `log-sum -> converse-log-sum` — misattributed proof chain.
- `rhominus-nonneg -> rho-subgroup` — incorrect dependency direction.

---

## 6. Summary

| Aspect | Bp vs Manual | Bp vs Inferred | Man vs Inferred |
|--------|-------------|----------------|-----------------|
| Common nodes | 218 | 218 | 218 |
| Direct edge F1 | **0.998** | **0.826** | **0.823** |
| Style match rate | 100% | 96.4% | 96.4% |
| Path-based recall | 1.000 | 0.814 | 0.811 |
| Path-based precision | 0.998 | 0.921 | 0.921 |
| Reachability F1 | **0.999** | **0.851** | **0.850** |
| Truly spurious edges | 1 | 27 | 27 |

**Strengths of KnowTeX Manual mode:**

- Near-perfect agreement with the Lean Blueprint (F1 = 0.998, reachability F1 = 0.999)
- 100% edge style accuracy on matching edges
- Only 1 edge difference with the Blueprint: the Manual has `eta-def-multi -> tau-def-multi` (dashed) instead of `eta-def-multi -> k-vanish` (solid)

**Strengths of KnowTeX Inferred mode:**

- Good precision (0.898): most edges it produces are correct
- 308 out of 403 Blueprint edges recovered without any annotations (76.4%)
- All 11 style mismatches with the Blueprint are actually correct based on textual evidence (see Section 3.2); the difference is a convention mismatch, not an error

**Weaknesses of KnowTeX Inferred mode:**

- Misses ~24% of edges, split roughly evenly between dashed (statement-level `\uses` dependencies) and solid (proof-level) edges
- The rho/phi-minimizer subgraph is substantially disconnected
- The kl-div node is entirely disconnected from its outgoing edges
- Hub nodes `pfr_aux-improv` and `pfr_aux_torsion` lose most of their incoming edges
- 27 truly spurious edges from heuristic shortcuts
- 35 extra edges total, including sibling misidentification among pfr variants
- 11 style mismatches with the Blueprint, though these reflect a convention difference rather than errors (see Section 3.2)

**Key takeaway:** The Manual mode faithfully reproduces the expert-curated Blueprint structure (F1 = 0.998). The Inferred mode recovers ~76% of edges from text alone, but the 24% gap concentrates in structurally important definition-level dependencies, hub-node connections, and cross-chapter references that require explicit annotation to capture.
