# Chicago Notes Benchmark

Runs KnowTex's dependency inference rules on the MathGloss Chicago Notes
dataset, read directly with the Markdown front-end, and compares the result
against the hyperlinks in the source. All rules run; only D2 and D4 fire,
because the corpus has no proofs.

**Read [Interpreting the results](#interpreting-the-results) before quoting
any number from this benchmark.** The D2 figures validate the pipeline; they
are not an accuracy measurement. The per-rule D4 figures are not meaningful
as computed.

The results of the earlier version of this benchmark, which converted the
markdown to LaTeX first and is the version described in the paper
(arXiv:2601.15294v2, Section 5.3), are kept unchanged in
[`old_version/`](old_version/) together with its README and the manual
review of its D4 edges.

## Dataset

611 mathematics definitions from the
[MathGloss](https://github.com/MathGloss/MathGloss) project's `chicago/`
directory. Each definition is a markdown file with a YAML `title:` and
hyperlinks to other definitions. These hyperlinks form the ground truth
dependency edges (1667 edges). A link counts even when its text is empty
(`[](.../chicago/infimum)`) or its target has a sub-path
(`chicago/definitions/vector_space`, only the last path segment names the
definition); target slugs are matched case-insensitively (`Borel_space` vs.
`borel_space`).

## Method

1. **Download**: the markdown files and a Wikidata mapping CSV are fetched
   from the MathGloss repository into `data/`.
2. **Parse**: each markdown file is read to extract the title, body,
   inter-definition links and Wikidata ID; the links give the ground truth.
3. **KnowTex**: the files are concatenated in file-name order, with a
   blank line between them, and handed to KnowTex's Markdown front-end
   (`knowtex/core/text_parser.py`) as one document. Nothing is converted,
   rewritten or reordered. The front-end reads the YAML `title:` as the
   defined term of each entry and the hyperlinks as references;
   `run_inference` then runs every rule with `definition` as the
   definition-like kind and `ordered=False`: a set of files has no reading
   order, so D4's "the definition comes before the statement that uses the
   term" check is switched off and a term is matched in every other entry.
   No other rule is changed.
4. **Evaluation**: inferred edges are compared against the ground truth.
   Precision, recall and F1 are reported per rule and combined. The
   front-end labels nodes `definition:<slug>`; the script maps them to the
   `def:<slug>` labels of the ground truth.

## Results

Run `run_20260929_192840.json`, ground truth 1667 edges:

| Rule | Inferred | TP | FP | FN | Precision | Recall | F1 |
| ---- | -------- | -- | -- | -- | --------- | ------ | -- |
| D2 | 1667 | 1667 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| D4 | 616 | 0 | 616 | 1667 | 0.000 | 0.000 | 0.000 |
| All rules | 2283 | 1667 | 616 | 0 | 0.730 | 1.000 | 0.844 |

### D4 alone (ablation)

`--d4-only` reduces every hyperlink to its text before parsing, so D2 finds
nothing and every ground-truth edge is left for D4 to find or miss. The
text and the ground truth stay the author's; only the signal D2 uses is
removed. Run `run_20260929_193416_d4-only.json`:

| Rule | Inferred | TP | FP | FN | Precision | Recall | F1 |
| ---- | -------- | -- | -- | -- | --------- | ------ | -- |
| D4 alone | 1884 | 1268 | 616 | 399 | 0.673 | 0.761 | 0.714 |

This is the number to quote for D4. The 616 false positives are the same
616 edges that appear as D4 in the full run; the 1268 true positives are
the edges D2 owns there.

What the ablation shows (from the `*_d4-only.csv` files):

- **Misses (399)**: in 381 of them the defined term does not occur in the
  target's text at all. The author linked a page under a different wording
  than its title, e.g. `[modules](…/module_over_a_ring)` or
  `[algebra](…/algebra_over_a_field)`; the link text is a fragment or an
  inflection of a multi-word title. The largest sources of misses are
  `module-over-a-ring` (23), `dimension-of-vector-space` (18),
  `polynomial-ring` (18) and `algebra-over-a-field` (14). Only 18 misses
  have the title verbatim in the text.
- **False positives (616)**: 517 come from single-word terms; `functional`
  alone gives 108 (its stem "function" matches everywhere), then `group`
  (33), `measurable` (25), `derivation` (21), `closed` (20), `class` (18).
  182 of the 616 targets are reachable from the source through
  ground-truth links, i.e. the dependency exists in the corpus but was
  never written as a direct link.

## Interpreting the results

### D2: a pipeline validation, not an accuracy measurement

The ground truth edges and the references that D2 reads are the same
information: both are the hyperlinks of the markdown files. D2 reaching
precision 1.0 and recall 1.0 is therefore expected by construction. It does
**not** say that D2 finds dependencies well in real documents. What it does
say is useful, but different: on 611 definitions and 1667 links, the Markdown
front-end, label resolution and edge direction lost nothing and inverted
nothing. Quote the D2 result as a pipeline check, never as an accuracy
figure.

### D4: the per-rule numbers are not meaningful as computed

`run_inference` deduplicates edges by `(source, target)` and the first rule
to add an edge owns it. D2 runs before D4. Every ground truth edge is a link,
so D2 has already claimed it before D4 runs. The only edges that can be
attributed to D4 are therefore edges that D2 did not produce, and those are,
by construction, outside the ground truth. `tp = 0, precision = 0.0` for D4
in the full run is a certainty of the setup, not a measurement. Do not read
it as "D4 does not work"; the `--d4-only` ablation above measures D4.

### D4 false positives are an upper bound on errors

The ground truth is partial: an author who did not add a link did not
thereby assert that there is no dependency. Example: `ring.md` links the
words *abelian* and *group* separately, so the ground truth contains
`abelian → ring` and `group → ring` but not `abelian-group → ring`. D4 sees
the phrase "abelian group" in the ring definition and adds
`abelian-group → ring`, which is mathematically correct but is counted as a
false positive.

Other D4 false positives are genuine over-matching, mostly from single-word
defined terms such as *functional*, whose stem "function" matches any
definition whose text contains that word. The benchmark cannot separate
these two kinds of false positive automatically; `fp_edges.csv` lists them
for manual review.

## Usage

```bash
# First run (downloads data)
python3 benchmark/chicago_benchmark.py

# Skip download (when data/ already exists)
python3 benchmark/chicago_benchmark.py --skip-download

# Download all files again, overwriting existing ones
python3 benchmark/chicago_benchmark.py --force-download

# Also write detailed edge-level CSVs
python3 benchmark/chicago_benchmark.py --skip-download --output-csv

# Ablation: links reduced to text, D4 scored alone (outputs get _d4-only)
python3 benchmark/chicago_benchmark.py --skip-download --output-csv --d4-only
```

## Outputs

Each run saves a timestamped JSON file to `data/results/`
(e.g. `run_20260929_192840.json`, or `run_*_d4-only.json` for the ablation)
containing:

- `timestamp` and `ground_truth_total`
- `combined`: precision, recall, F1 and edge counts (TP, FP, FN, inferred total)
- `per_rule`: the same metrics for each rule that fired
- `note`: a reminder that the ground truth holds hyperlink edges only

With `--output-csv`, three additional files are written (with the suffix
`_d4-only` in the ablation run):

- `tp_edges.csv` -- True Positive edges
- `fp_edges.csv` -- False Positive edges
- `fn_edges.csv` -- False Negative edges

Each row has `source_label`, `target_label`, the two Wikidata IDs,
`classification` (TP/FP/FN) and the `rules` that produced the edge.

## Directory Structure

```text
benchmark/
  chicago_benchmark.py   # Main benchmark script
  README.md              # This file
  old_version/           # Results and README of the LaTeX-conversion version (paper)
    README.md
    results/
      run_20260403_160000.json
      tp_edges.csv, fp_edges.csv, fn_edges.csv
      fp_classification.csv  # Manual review of that run's 433 D4 edges
  data/
    chicago_md/          # Downloaded markdown files
    chicago_mappings.csv # Wikidata mappings
    results/
      run_*.json         # Per-run metrics (run_*_d4-only.json: ablation)
      tp_edges*.csv      # True Positive edges (with --output-csv)
      fp_edges*.csv      # False Positive edges
      fn_edges*.csv      # False Negative edges
```
