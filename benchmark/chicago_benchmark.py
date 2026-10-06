#!/usr/bin/env python3
"""
Chicago Notes Benchmark for KnowTex
====================================

Downloads the MathGloss Chicago Notes definitions (611 markdown files),
reads them with KnowTex's Markdown front-end, runs the inference rules
(all rules; only D2 and D4 fire, because the corpus has no proofs) and
evaluates the result against the ground truth dependency edges given by
the inter-definition hyperlinks in the markdown source.

Usage:
    python3 benchmark/chicago_benchmark.py

Requirements:
    - Internet access (for the first run, to download the data)
    - KnowTex dependencies (PyStemmer or snowballstemmer)
"""

import argparse
import csv
from datetime import datetime
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from knowtex.core.data import DependencyEdge
from knowtex.core.formats import markdown_files, read_markdown_files
from knowtex.core.text_parser import parse_text_structure, slugify
from knowtex.core.cycles import find_cycles
from knowtex.deps.infer import run_inference, resolve_cycles

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
CHICAGO_MD_DIR = DATA_DIR / "chicago_md"
MAPPINGS_FILE = DATA_DIR / "chicago_mappings.csv"

GITHUB_API_TREE = "https://api.github.com/repos/MathGloss/MathGloss/git/trees/main"
GITHUB_RAW = "https://raw.githubusercontent.com/MathGloss/MathGloss/main"
MAPPINGS_URL = f"{GITHUB_RAW}/data/alignments/chicago_mappings.csv"

# Regex to extract inter-definition links from markdown
# Pattern: [link text](https://mathgloss.github.io/MathGloss/chicago/TERM_NAME)
# The link text may be empty ("[](.../chicago/infimum)") and the target may
# carry a sub-path ("chicago/definitions/vector_space"); ``_link_key``
# reduces a target to the last path segment, lower-cased, so that it can be
# compared with the file slugs ("Borel_space" vs "borel_space").
LINK_RX = re.compile(
    r"\[([^\]]*)\]\(https?://mathgloss\.github\.io/MathGloss/chicago/([^)\s]+)\)"
)


def _link_key(target):
    """Normalise a link target to the key used for slug lookup."""
    return target.rstrip("/").rsplit("/", 1)[-1].lower()

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

def build_ground_truth(defs):
    """Build the ground truth edge set from inter-definition links.

    An edge (def:A, def:B) means "B depends on (uses) A".
    This is derived from B's markdown linking to A.
    """
    # Build slug lookup (case-insensitive, last path segment only)
    slug_to_def = {d.slug.lower(): d for d in defs}

    edges = set()
    for d in defs:
        for _link_text, target in d.links:
            key = _link_key(target)
            if key in slug_to_def and key != d.slug.lower():
                source_label = slug_to_def[key].label
                target_label = d.label
                edges.add((source_label, target_label))

    print(f"Ground truth: {len(edges)} edges from inter-definition links.")
    return edges


# ---------------------------------------------------------------------------
# KnowTex inference
# ---------------------------------------------------------------------------

# Markdown links, kept as their text: "[abelian group](…/abelian_group)" -> "abelian group"
MD_LINK_RX = re.compile(r"\[([^\]]*)\]\([^)]*\)")

RUN_SUFFIX = ""   # "_d4-only" for the ablation run


def run_knowtex(defs, d4_only=False):
    """Run KnowTex's Markdown front-end and inference rules on the files.

    The folder is read exactly as the GUI reads a folder of Markdown files
    (``formats.read_markdown_files``: file-name order, a blank line between
    files) and parsed by ``knowtex.core.text_parser``, which reads
    the YAML ``title:`` as the defined term and the hyperlinks as
    references.  The front-end labels nodes ``definition:<slug>``; they
    are mapped to the ``def:<slug>`` labels of the ground truth here.

    With *d4_only* the hyperlinks are reduced to their text before parsing,
    so D2 has nothing to read and every ground-truth edge is left for D4
    to find (or miss).  The text and the ground truth stay the author's;
    only the signal D2 uses is removed.
    """
    text = read_markdown_files(markdown_files(CHICAGO_MD_DIR))
    if d4_only:
        text = MD_LINK_RX.sub(r"\1", text)
    nodes, node_by_index, label_to_node, proofs, envs = parse_text_structure(text)
    print(f"KnowTex parsed: {len(nodes)} nodes, {len(proofs)} proofs")
    # Several files, no reading order: D4 matches in every entry.
    edges = run_inference(nodes, node_by_index, label_to_node, proofs,
                          definition_envs={"definition"}, ordered=False)

    # Cycle resolution: the D4 edges that close a cycle are dropped,
    # weakest evidence first, until only the author's own cycles remain
    # (``resolve_cycles``; the rules themselves are unchanged).
    cycle_edges_before = len(find_cycles(edges))
    edges, dropped = resolve_cycles(edges, nodes)
    cycle_edges_after = len(find_cycles(edges))
    print(f"Cycle resolution: {cycle_edges_before} cycle edges before, "
          f"{cycle_edges_after} after; {len(dropped)} D4 edges dropped")

    # The Markdown front-end slugifies titles (apostrophes dropped, case
    # folded); do the same to the ground-truth side so labels line up.
    title_slug_to_gt = {}
    for d in defs:
        title_slug_to_gt[slugify(d.title)] = d.label
        title_slug_to_gt[slugify(d.slug)] = d.label

    def to_gt(label):
        slug = label.split(":", 1)[1]
        return title_slug_to_gt.get(slug, "def:" + slug)

    mapped = [DependencyEdge(to_gt(e.source), to_gt(e.target),
                             e.edge_type, e.location, e.rule) for e in edges
              if not d4_only or e.rule == "D4"]
    counts = defaultdict(int)
    for e in mapped:
        counts[e.rule] += 1
    print(f"KnowTex inferred {len(mapped)} total edges:")
    for rule, count in sorted(counts.items()):
        print(f"  {rule}: {count}")
    cycle_info = {
        "cycle_edges_before_resolution": cycle_edges_before,
        "cycle_edges_after_resolution": cycle_edges_after,
        "dropped_total": len(dropped),
        "dropped_edges": [[to_gt(e.source), to_gt(e.target), e.rule] for e in dropped],
    }
    return mapped, cycle_info


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


def evaluate(all_edges, ground_truth, defs, output_csv=False, cycle_info=None):
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

    if cycle_info:
        print(f"  Cycle edges: {cycle_info['cycle_edges_before_resolution']} before "
              f"resolution, {cycle_info['cycle_edges_after_resolution']} after "
              f"({cycle_info['dropped_total']} D4 edges dropped)")
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
        "cycles": cycle_info,
        "note": ("The ground truth holds hyperlink edges only, so every D4 "
                 "edge counts as a false positive here; see benchmark/README.md."),
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
    outpath = out_dir / f"run_{ts}{RUN_SUFFIX}.json"
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
        outpath = out_dir / f"{name}_edges{RUN_SUFFIX}.csv"
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
        description="Chicago Notes Benchmark for KnowTex (Markdown front-end; only D2 and D4 fire on this corpus)"
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
    parser.add_argument(
        "--d4-only", action="store_true",
        help="Ablation: reduce the hyperlinks to their text so that D2 finds "
             "nothing, and score D4 alone against the same ground truth "
             "(outputs get the suffix _d4-only)",
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

    # Step 4: Run KnowTex on the markdown
    if args.d4_only:
        global RUN_SUFFIX
        RUN_SUFFIX = "_d4-only"
    all_edges, cycle_info = run_knowtex(defs, d4_only=args.d4_only)

    # Step 5: Evaluate
    results = evaluate(all_edges, ground_truth, defs, output_csv=args.output_csv,
                       cycle_info=cycle_info)

    return results


if __name__ == "__main__":
    main()
