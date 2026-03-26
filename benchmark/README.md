# Chicago Notes Benchmark

Evaluates KnowTex's dependency inference rules (D2, D4) against the
MathGloss Chicago Notes dataset.

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
   into LaTeX `definition` environments. Inter-definition hyperlinks become
   `\ref{}` commands so that the D2 (cross-reference) rule can fire.
4. **KnowTex inference**: `parse_latex_structure` and `run_inference` are
   executed on the generated LaTeX.
5. **Evaluation**: Inferred edges are compared against the ground truth.
   Precision, recall, and F1 are reported per rule (D2, D4) and combined.

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
