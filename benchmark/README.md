# Chicago Notes Benchmark

Runs KnowTex's dependency inference rules (D2, D4) on the MathGloss Chicago
Notes dataset and compares the result against the hyperlinks in the source.

**Read [Interpreting the results](#interpreting-the-results) before quoting
any number from this benchmark.** The D2 figures validate the pipeline; they
are not an accuracy measurement. The per-rule D4 figures are not meaningful
as currently computed.

## Dataset

~611 mathematics definitions from the
[MathGloss](https://github.com/MathGloss/MathGloss) project's `chicago/`
directory. Each definition is a markdown file containing hyperlinks to other
definitions. These hyperlinks form the ground truth dependency edges.

## Method

1. **Download**: Markdown files and a Wikidata mapping CSV are fetched from
   the MathGloss repository.
2. **Parse**: Each markdown file is parsed to extract the title, body,
   inter-definition links, and Wikidata ID.
3. **LaTeX generation**: Definitions are topologically sorted and converted
   into LaTeX `definition` environments. The conversion is kept as literal
   as possible; every decision is listed here so the reader can judge it:
   - Each inter-definition hyperlink becomes `linked text~\ref{label}`.
     This preserves the link that is already in the source; nothing is
     added.
   - The page title is placed at the start of the body as `\emph{title}`.
     The markdown marks the defined term in **bold**; the page title is
     the same term, so this is the LaTeX convention for the same markup.
     Bold markers themselves are stripped.
   - `*italic*` is **not** converted to `\emph{}`, because `*` also appears
     inside math and a naive rewrite would break it.
   - Math (`$...$`) and the rest of the text are copied verbatim.
   - The Wikidata line is removed.
4. **KnowTex inference**: `parse_latex_structure` and `run_inference` are
   executed on the generated LaTeX.
5. **Evaluation**: Inferred edges are compared against the ground truth.
   Precision, recall, and F1 are reported per rule (D2, D4) and combined.
   See the next section for what these numbers do and do not mean.

## Interpreting the results

### D2: a pipeline validation, not an accuracy measurement

The ground truth edges and the `\ref{}` commands that D2 reads are the same
information in two encodings. Both come from the hyperlink list of each
markdown file: one copy is written into the ground truth set, the other is
written into the generated LaTeX. D2 then reads the second copy and is
compared against the first.

Consequently, D2 reaching precision 1.0 and recall 1.0 is expected by
construction. It does **not** say that D2 finds dependencies well in real
documents. What it does say is useful, but different: on 611 definitions and
1660 edges, the LaTeX generation, the parser, label resolution, and edge
direction lost nothing and inverted nothing. Quote the D2 result as a
pipeline check, never as an accuracy figure.

### D4: the per-rule numbers are not meaningful as computed

`run_inference` deduplicates edges by `(source, target)` and the first rule
to add an edge owns it. D2 runs before D4. Every ground truth edge has a
`\ref{}`, so D2 has already claimed it before D4 runs. The only edges that
can be attributed to D4 are therefore edges that D2 did not produce, and
those are, by construction, outside the ground truth.

This makes `D4: tp = 0, precision = 0.0` a certainty of the setup, not a
measurement. Do not read it as "D4 does not work".

### D4 false positives are an upper bound on errors

The ground truth is partial: an author who did not add a link did not
thereby assert that there is no dependency. Example: `ring.md` links the
words *abelian* and *group* separately, so the ground truth contains
`abelian → ring` and `group → ring` but not `abelian-group → ring`. D4 sees
the phrase "abelian group" in the ring definition and adds
`abelian-group → ring`, which is mathematically correct but is counted as a
false positive.

Other D4 false positives are genuine over-matching. Single-word defined
terms are the main source: the term *functional* alone produces 31 edges to
any definition whose text contains that word. The current benchmark cannot
separate these two kinds of false positive automatically.

### What could measure D4 honestly

Neither of these is implemented; they are recorded here so that the
limitation is not mistaken for an oversight.

- **Recall via ablation**: generate the LaTeX with links reduced to plain
  text (no `\ref{}`) and run D4 alone against the same ground truth. The
  text and the ground truth stay the author's; only the signal D2 uses is
  removed. This mirrors the PFR comparison, where `\uses{}` was removed to
  evaluate infer mode.
- **Precision via manual annotation**: label a random sample of D4 false
  positives by hand as "real dependency, unlinked by the author" or
  "spurious match", and report the fraction.

## Usage

```bash
# First run (downloads data)
python3 benchmark/chicago_benchmark.py

# Skip download (when data/ already exists)
python3 benchmark/chicago_benchmark.py --skip-download

# Also write detailed edge-level CSVs
python3 benchmark/chicago_benchmark.py --output-csv
```

## Outputs

Each run saves a timestamped JSON file to `data/results/`
(e.g. `run_20260326_143012.json`) containing:

- Per-rule metrics (precision, recall, F1)
- Combined metrics
- Edge counts (TP, FP, FN)
- Timestamp

With the `--output-csv` flag, three additional files are written:

- `tp_edges.csv` -- True Positive edges
- `fp_edges.csv` -- False Positive edges
- `fn_edges.csv` -- False Negative edges

## Directory Structure

```text
benchmark/
  chicago_benchmark.py   # Main benchmark script
  README.md              # This file
  data/
    chicago_md/          # Downloaded markdown files
    chicago_mappings.csv # Wikidata mappings
    chicago_notes.tex    # Generated LaTeX file
    results/
      run_*.json         # Per-run metrics
      tp_edges.csv       # True Positive edges
      fp_edges.csv       # False Positive edges
      fn_edges.csv       # False Negative edges
```
