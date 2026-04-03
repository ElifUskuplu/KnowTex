#!/usr/bin/env python3
"""
Chicago Notes Benchmark for KnowTex
====================================

Downloads MathGloss Chicago Notes definitions (~611 math definitions),
converts them to LaTeX with \\ref{} cross-references, runs KnowTex
inference (D2 + D4), and evaluates against ground truth dependency
edges extracted from inter-definition hyperlinks in the markdown source.

Usage:
    python3 benchmark/chicago_benchmark.py

Requirements:
    - Internet access (for first run to download data)
    - KnowTex dependencies (pylatexenc, PyStemmer)
"""

import argparse
import csv
from datetime import datetime
import json
import heapq
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from knowtex.core.parser import parse_latex_structure
from knowtex.deps.infer import run_inference

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
CHICAGO_MD_DIR = DATA_DIR / "chicago_md"
MAPPINGS_FILE = DATA_DIR / "chicago_mappings.csv"
GENERATED_TEX = DATA_DIR / "chicago_notes.tex"

GITHUB_API_TREE = "https://api.github.com/repos/MathGloss/MathGloss/git/trees/main"
GITHUB_RAW = "https://raw.githubusercontent.com/MathGloss/MathGloss/main"
MAPPINGS_URL = f"{GITHUB_RAW}/data/alignments/chicago_mappings.csv"

# Regex to extract inter-definition links from markdown
# Pattern: [link text](https://mathgloss.github.io/MathGloss/chicago/TERM_NAME)
LINK_RX = re.compile(
    r"\[([^\]]+)\]\(https?://mathgloss\.github\.io/MathGloss/chicago/([^)]+)\)"
)

# YAML frontmatter
FRONTMATTER_RX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TITLE_RX = re.compile(r"^title:\s*(.+)$", re.MULTILINE)

# Wikidata ID from body
WIKIDATA_RX = re.compile(r"Wikidata ID:\s*\[Q(\d+)\]")


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _fetch(url):
    """Fetch a URL and return the response body as a string."""
    req = urllib.request.Request(url, headers={"User-Agent": "KnowTex-Benchmark/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _fetch_chicago_tree():
    """Get the list of .md filenames in the chicago/ directory via GitHub API."""
    # First get the SHA of the chicago/ tree
    data = json.loads(_fetch(GITHUB_API_TREE))
    chicago_sha = None
    for item in data["tree"]:
        if item["path"] == "chicago" and item["type"] == "tree":
            chicago_sha = item["sha"]
            break
    if not chicago_sha:
        raise RuntimeError("Could not find chicago/ directory in MathGloss repo")

    # Get the tree for chicago/
    tree_url = f"https://api.github.com/repos/MathGloss/MathGloss/git/trees/{chicago_sha}"
    tree_data = json.loads(_fetch(tree_url))
    md_files = [
        item["path"]
        for item in tree_data["tree"]
        if item["path"].endswith(".md")
    ]
    return md_files


def download_data(force=False):
    """Download Chicago markdown files and mappings CSV from MathGloss."""
    CHICAGO_MD_DIR.mkdir(parents=True, exist_ok=True)

    # Download mappings CSV
    if force or not MAPPINGS_FILE.exists():
        print("Downloading chicago_mappings.csv...")
        content = _fetch(MAPPINGS_URL)
        MAPPINGS_FILE.write_text(content, encoding="utf-8")
        print(f"  Saved {MAPPINGS_FILE}")

    # Check if we already have markdown files
    existing = list(CHICAGO_MD_DIR.glob("*.md"))
    if not force and len(existing) > 500:
        print(f"Found {len(existing)} existing markdown files, skipping download.")
        return

    # Get list of .md files from GitHub API
    print("Fetching file list from GitHub API...")
    md_files = _fetch_chicago_tree()
    print(f"  Found {len(md_files)} markdown files")

    # Download each file
    downloaded = 0
    skipped = 0
    for i, fname in enumerate(md_files):
        dest = CHICAGO_MD_DIR / fname
        if not force and dest.exists():
            skipped += 1
            continue
        url = f"{GITHUB_RAW}/chicago/{urllib.request.quote(fname)}"
        try:
            content = _fetch(url)
            dest.write_text(content, encoding="utf-8")
            downloaded += 1
            if downloaded % 50 == 0:
                print(f"  Downloaded {downloaded}/{len(md_files) - skipped}...")
        except urllib.error.HTTPError as e:
            print(f"  WARNING: Failed to download {fname}: {e}")

    print(f"  Done: {downloaded} downloaded, {skipped} already existed.")


# ---------------------------------------------------------------------------
# Parse markdown files
# ---------------------------------------------------------------------------

class ChicagoDef:
    """A parsed Chicago definition."""
    __slots__ = ("filename", "title", "body", "links", "wikidata_id")

    def __init__(self, filename, title, body, links, wikidata_id):
        self.filename = filename      # e.g. "group.md"
        self.title = title            # e.g. "group"
        self.body = body              # markdown body (without frontmatter)
        self.links = links            # list of (link_text, target_slug) tuples
        self.wikidata_id = wikidata_id  # e.g. "Q83478" or None

    @property
    def slug(self):
        """Filename without .md extension."""
        return self.filename[:-3] if self.filename.endswith(".md") else self.filename

    @property
    def label(self):
        """KnowTex-style label: def:slug-with-hyphens."""
        return "def:" + self.slug.lower().replace("_", "-").replace(" ", "-")


def parse_markdown(filepath):
    """Parse a Chicago definition markdown file."""
    text = filepath.read_text(encoding="utf-8")
    filename = filepath.name

    # Extract frontmatter
    title = filename[:-3].replace("_", " ")  # fallback
    fm = FRONTMATTER_RX.match(text)
    if fm:
        tm = TITLE_RX.search(fm.group(1))
        if tm:
            title = tm.group(1).strip()
        body = text[fm.end():]
    else:
        body = text

    # Extract links to other Chicago definitions
    links = []
    for m in LINK_RX.finditer(body):
        link_text = m.group(1)
        target_slug = m.group(2)
        links.append((link_text, target_slug))

    # Extract Wikidata ID
    wikidata_id = None
    wm = WIKIDATA_RX.search(body)
    if wm:
        wikidata_id = f"Q{wm.group(1)}"

    return ChicagoDef(filename, title, body, links, wikidata_id)


def load_all_definitions():
    """Load and parse all Chicago markdown files."""
    md_files = sorted(CHICAGO_MD_DIR.glob("*.md"))
    if not md_files:
        raise RuntimeError(
            f"No markdown files found in {CHICAGO_MD_DIR}. Run with download first."
        )

    defs = []
    for f in md_files:
        try:
            d = parse_markdown(f)
            defs.append(d)
        except Exception as e:
            print(f"  WARNING: Failed to parse {f.name}: {e}")

    print(f"Parsed {len(defs)} definitions from markdown files.")
    return defs


# ---------------------------------------------------------------------------
# Markdown → LaTeX conversion
# ---------------------------------------------------------------------------

def _md_to_latex_body(body, slug_to_label):
    """Convert markdown body to LaTeX text.

    - **bold** → plain text (strip asterisks; the definition title is used as \\emph{} instead)
    - [linked text](chicago/TARGET) → linked text~\\ref{label} (marks usage of other terms)
    - $math$ stays as-is
    - Strip Wikidata line
    """
    # Remove the Wikidata ID line
    text = re.sub(r"Wikidata ID:.*$", "", body, flags=re.MULTILINE).strip()

    # First pass: replace **bold with [link](...)** inside bold
    # to avoid nested \emph. Extract bold spans, replace links inside them,
    # then wrap the whole thing in one \emph{}.
    def replace_bold(m):
        inner = m.group(1)
        # Convert links inside bold spans to \ref{} but don't wrap in \emph{}
        def bold_link(lm):
            link_text = lm.group(1)
            target_slug = lm.group(2)
            label = slug_to_label.get(target_slug)
            if label:
                return f"{link_text}~\\ref{{{label}}}"
            return link_text
        inner = LINK_RX.sub(bold_link, inner)
        return inner  # plain text, no \emph{}

    text = re.sub(r"\*\*([^*]+)\*\*", replace_bold, text)

    # Replace Chicago inter-definition links with text~\ref{label}.
    # This enables D2 (cross-reference rule) to fire on these dependencies.
    def replace_link(m):
        link_text = m.group(1)
        target_slug = m.group(2)
        label = slug_to_label.get(target_slug)
        if label:
            return f"{link_text}~\\ref{{{label}}}"
        return link_text
    text = LINK_RX.sub(replace_link, text)

    # Note: We intentionally do NOT convert *italic* markdown to \emph{}.
    # The `*` character appears in LaTeX math environments (e.g. align*, V^*)
    # and a naive regex would break them. The few italic uses (~4 instances
    # like *not*) are not critical for D4 term matching.

    # Replace remaining markdown links (including empty-text links)
    text = re.sub(r"\[[^\]]*\]\([^)]+\)", lambda m: re.search(r"\[([^\]]*)\]", m.group()).group(1), text)

    # Clean up markdown formatting
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)  # headers
    text = text.replace("\\|", "|")  # escaped pipes

    return text.strip()


def _topological_sort(defs):
    """Sort definitions so that depended-upon definitions come first.

    Uses Kahn's algorithm. Definitions with no dependencies come first,
    then definitions whose dependencies are all already placed, etc.
    Ties are broken alphabetically. Cycles are broken arbitrarily.
    """
    slug_set = {d.slug for d in defs}
    slug_to_def = {d.slug: d for d in defs}

    # Build adjacency: for each def, which slugs does it depend on?
    deps_of = {}  # slug -> set of slugs it depends on
    dependents_of = defaultdict(set)  # slug -> set of slugs that depend on it
    for d in defs:
        dep_slugs = set()
        for _link_text, target_slug in d.links:
            if target_slug in slug_set and target_slug != d.slug:
                dep_slugs.add(target_slug)
        deps_of[d.slug] = dep_slugs
        for dep in dep_slugs:
            dependents_of[dep].add(d.slug)

    # Kahn's algorithm with a min-heap for efficient sorted extraction
    in_degree = {d.slug: len(deps_of[d.slug]) for d in defs}
    heap = [(slug_to_def[s].title.lower(), s) for s, deg in in_degree.items() if deg == 0]
    heapq.heapify(heap)
    result = []
    while heap:
        _key, slug = heapq.heappop(heap)
        result.append(slug_to_def[slug])
        for dep in dependents_of[slug]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                heapq.heappush(heap, (slug_to_def[dep].title.lower(), dep))

    # Append any remaining (cycle members) alphabetically
    placed = {d.slug for d in result}
    remaining = sorted(
        [d for d in defs if d.slug not in placed],
        key=lambda d: d.title.lower(),
    )
    result.extend(remaining)
    return result


def generate_latex(defs):
    """Generate a complete LaTeX document from parsed definitions."""
    slug_to_label = {d.slug: d.label for d in defs}

    lines = [
        r"\documentclass[12pt,a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb,amsthm}",
        r"\usepackage{hyperref}",
        "",
        r"\theoremstyle{definition}",
        r"\newtheorem{definition}{Definition}",
        "",
        r"\title{Chicago Notes -- MathGloss Definitions}",
        r"\author{Auto-generated for KnowTex Benchmark}",
        r"\date{}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]

    # Topological sort: definitions that are depended upon come first.
    # This ensures D4's forward-reference guard (src_index < ni.index)
    # doesn't cause systematic false negatives.
    sorted_defs = _topological_sort(defs)

    for d in sorted_defs:
        # Convert title to a LaTeX-safe display name
        safe_title = d.title.replace("_", " ")
        safe_title = safe_title.replace("\\", r"\textbackslash{}")
        safe_title = re.sub(r"([#%&_{}~^$])", r"\\\1", safe_title)

        body = _md_to_latex_body(d.body, slug_to_label)
        if not body:
            continue

        lines.append(f"\\begin{{definition}}[{safe_title}]\\label{{{d.label}}}")
        # Use the full title as the defined term for D4 extraction.
        # For multi-word titles, D4 uses contiguous phrase matching
        # which is much more precise than single-word stem matching.
        lines.append(f"\\emph{{{safe_title}}}. {body}")
        lines.append(r"\end{definition}")
        lines.append("")

    lines.append(r"\end{document}")
    tex = "\n".join(lines)

    GENERATED_TEX.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_TEX.write_text(tex, encoding="utf-8")
    print(f"Generated LaTeX file: {GENERATED_TEX} ({len(sorted_defs)} definitions)")
    return tex


# ---------------------------------------------------------------------------
# Ground truth extraction
# ---------------------------------------------------------------------------

def build_ground_truth(defs):
    """Build the ground truth edge set from inter-definition links.

    An edge (def:A, def:B) means "B depends on (uses) A".
    This is derived from B's markdown linking to A.
    """
    # Build slug lookup
    slug_set = {d.slug for d in defs}
    slug_to_def = {d.slug: d for d in defs}

    edges = set()
    for d in defs:
        for _link_text, target_slug in d.links:
            if target_slug in slug_set and target_slug != d.slug:
                source_label = slug_to_def[target_slug].label
                target_label = d.label
                edges.add((source_label, target_label))

    print(f"Ground truth: {len(edges)} edges from inter-definition links.")
    return edges


# ---------------------------------------------------------------------------
# KnowTex inference
# ---------------------------------------------------------------------------

def run_knowtex_inference(tex):
    """Run KnowTex's parser and inference (all rules) on the LaTeX text."""
    nodes, node_by_index, label_to_node, proofs, envs = parse_latex_structure(tex)

    print(f"KnowTex parsed: {len(nodes)} nodes, {len(proofs)} proofs")
    print(f"  Environments found: {envs}")

    edges = run_inference(
        nodes, node_by_index, label_to_node, proofs,
        definition_envs={"definition"},
    )
    all_edge_rules = defaultdict(int)
    for e in edges:
        all_edge_rules[e.rule] += 1

    print(f"KnowTex inferred {len(edges)} total edges:")
    for rule, count in sorted(all_edge_rules.items()):
        print(f"  {rule}: {count}")

    return edges


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _compute_metrics(inferred, ground_truth):
    """Compute precision, recall, F1 for an inferred edge set."""
    tp = inferred & ground_truth
    fp = inferred - ground_truth
    fn = ground_truth - inferred
    precision = len(tp) / len(tp | fp) if (tp | fp) else 0.0
    recall = len(tp) / len(tp | fn) if (tp | fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return tp, fp, fn, precision, recall, f1


def evaluate(all_edges, ground_truth, defs, output_csv=False):
    """Compute precision, recall, F1 per rule and print a report."""
    # Build per-rule edge sets
    rule_sets = {}
    edge_to_rules = defaultdict(set)
    for e in all_edges:
        key = (e.source, e.target)
        edge_to_rules[key].add(e.rule)

    all_rules = sorted({e.rule for e in all_edges})
    for rule in all_rules:
        rule_sets[rule] = {(e.source, e.target) for e in all_edges if e.rule == rule}

    if len(all_rules) > 1:
        rule_sets["All rules"] = {(e.source, e.target) for e in all_edges}

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS: KnowTex vs MathGloss Ground Truth")
    print("=" * 60)
    print(f"  Ground truth edges: {len(ground_truth)}")
    print()

    for name, inferred in rule_sets.items():
        tp, fp, fn, precision, recall, f1 = _compute_metrics(inferred, ground_truth)
        print(f"  --- {name} ---")
        print(f"  Inferred edges:      {len(inferred)}")
        print(f"  True Positives (TP): {len(tp)}")
        print(f"  False Positives (FP):{len(fp)}")
        print(f"  False Negatives (FN):{len(fn)}")
        print(f"  Precision:           {precision:.4f}")
        print(f"  Recall:              {recall:.4f}")
        print(f"  F1 Score:            {f1:.4f}")
        print()

    print("=" * 60)

    # Build per-rule metrics for the result dict
    per_rule = {}
    for name, inferred in rule_sets.items():
        if name == "All rules":
            continue
        r_tp, r_fp, r_fn, r_prec, r_rec, r_f1 = _compute_metrics(inferred, ground_truth)
        per_rule[name] = {
            "precision": r_prec,
            "recall": r_rec,
            "f1": r_f1,
            "tp": len(r_tp),
            "fp": len(r_fp),
            "fn": len(r_fn),
            "inferred_total": len(inferred),
        }

    # Use combined edge set for CSV output, samples, and return value
    all_inferred = {(e.source, e.target) for e in all_edges}
    tp, fp, fn, precision, recall, f1 = _compute_metrics(all_inferred, ground_truth)
    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "ground_truth_total": len(ground_truth),
        "combined": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": len(tp),
            "fp": len(fp),
            "fn": len(fn),
            "inferred_total": len(all_inferred),
        },
        "per_rule": per_rule,
    }

    # Save results JSON
    _save_run_json(result)

    if output_csv:
        _write_results_csv(tp, fp, fn, defs, edge_to_rules)

    # Print a few example TP, FP, FN for inspection
    print("\nSample True Positives (max 5):")
    for src, tgt in sorted(tp)[:5]:
        rules = ", ".join(sorted(edge_to_rules.get((src, tgt), set())))
        print(f"  {src} → {tgt}  [{rules}]")

    print("\nSample False Positives (max 10):")
    for src, tgt in sorted(fp)[:10]:
        rules = ", ".join(sorted(edge_to_rules.get((src, tgt), set())))
        print(f"  {src} → {tgt}  [{rules}]")

    print("\nSample False Negatives (max 10):")
    for src, tgt in sorted(fn)[:10]:
        print(f"  {src} → {tgt}")

    return result


def _save_run_json(result):
    """Save benchmark results to a timestamped JSON file."""
    out_dir = DATA_DIR / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = out_dir / f"run_{ts}.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"  Saved results to {outpath}")


def _write_results_csv(tp, fp, fn, defs, edge_to_rules=None):
    """Write detailed edge-level results to CSV files."""
    label_to_wikidata = {}
    for d in defs:
        if d.wikidata_id:
            label_to_wikidata[d.label] = d.wikidata_id

    out_dir = DATA_DIR / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, edge_set in [("tp", tp), ("fp", fp), ("fn", fn)]:
        outpath = out_dir / f"{name}_edges.csv"
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "source_label", "target_label",
                "source_wikidata", "target_wikidata",
                "classification", "rules",
            ])
            for src, tgt in sorted(edge_set):
                rules = ""
                if edge_to_rules:
                    rules = ", ".join(sorted(edge_to_rules.get((src, tgt), set())))
                writer.writerow([
                    src, tgt,
                    label_to_wikidata.get(src, ""),
                    label_to_wikidata.get(tgt, ""),
                    name.upper(),
                    rules,
                ])
        print(f"  Wrote {outpath} ({len(edge_set)} edges)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Chicago Notes Benchmark for KnowTex (D2 + D4 rules)"
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip downloading data (use existing files)",
    )
    parser.add_argument(
        "--output-csv", action="store_true",
        help="Write detailed TP/FP/FN edge lists to CSV files",
    )
    parser.add_argument(
        "--force-download", action="store_true",
        help="Force re-download of all files",
    )
    args = parser.parse_args()

    # Step 1: Download data
    if not args.skip_download:
        download_data(force=args.force_download)
    else:
        print("Skipping download (--skip-download).")

    # Step 2: Parse markdown files
    defs = load_all_definitions()

    # Step 3: Build ground truth from inter-definition links
    ground_truth = build_ground_truth(defs)

    # Step 4: Generate LaTeX
    tex = generate_latex(defs)

    # Step 5: Run KnowTex inference
    all_edges = run_knowtex_inference(tex)

    # Step 6: Evaluate
    results = evaluate(all_edges, ground_truth, defs, output_csv=args.output_csv)

    return results


if __name__ == "__main__":
    main()
