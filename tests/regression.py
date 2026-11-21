#!/usr/bin/env python3
"""Regression check for the four datasets of the article.

``tests/datasets.py`` says how each graph is built (input file, mode,
statement kinds kept).  For every dataset and mode this script runs the
headless pipeline (``knowtex.pipeline.run_pipeline``) with that
configuration and compares the edges with the stored graph:

    example/group_theory-knowtex/inferred-graph-groups.dot         Case Study 1
    example/group_theory_with_uses-knowtex/manual-graph-groups.dot
    BCT-condensed/BCT-knowtex/inferred-graph-BCT.dot              Case Study 2
    BCT-condensed/BCT_with_uses-knowtex/manual-graph-BCT.dot
    chicago_notes/data/results/chicago_infer.csv                  Case Study 3
    Polynomial-Freiman-Ruzsa/pfr_without_uses/print-knowtex/pfr_infer_graph.dot   Case Study 4
    Polynomial-Freiman-Ruzsa/pfr_with_uses/print-knowtex/pfr_manual_graph.dot

    python tests/regression.py              # compare with the stored graphs
    python tests/regression.py --write      # (re)write them (DOT and PNG, CSV for Chicago)
    python tests/regression.py --dataset bct --dataset pfr

Exit status: 0 when every edge set equals its stored graph, 1 on any
difference or missing file.  A dataset whose input is not present (the
Chicago corpus has to be downloaded first) is reported as skipped and
does not fail the check.

An edge is compared as ``(source, target, rule, style)``: the DOT files
carry the rule in each edge's tooltip and the location in its style
(solid = from a proof, dashed = from a statement, dotted = heuristic).
The edges are those of the final graph, after cycle resolution and,
except for Chicago, transitive reduction.  A change in the rules shows up
as added or removed edges; a change made on purpose rewrites the graphs
with ``--write`` and explains the diff.
"""

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowtex.core.constants import default_env_style  # noqa: E402
from knowtex.core.dot import build_dot  # noqa: E402
from knowtex.evaluation import PROJECT_ROOT, dot_edges, edge_style, run_dataset  # noqa: E402
from datasets import load_configs  # noqa: E402

COLUMNS = ("source", "target", "rule", "style")


def result_rows(res):
    return sorted((e.source, e.target, e.rule, edge_style(e)) for e in res.edges)


# ---------------------------------------------------------------------------
# stored graphs: DOT (plus PNG) or, for Chicago, CSV
# ---------------------------------------------------------------------------

def baseline_path(cfg, mode):
    spec = cfg["modes"][mode]
    if spec.get("dot"):
        return PROJECT_ROOT / spec["dot"]
    return PROJECT_ROOT / cfg["baseline_dir"] / f"{cfg['name']}_{mode}.csv"


def read_baseline(path):
    if path.suffix == ".dot":
        return sorted(dot_edges(path))
    with open(path, newline="", encoding="utf-8") as fh:
        r = csv.reader(fh)
        header = next(r, None)
        if tuple(header or ()) != COLUMNS:
            raise ValueError(f"{path}: unexpected header {header}")
        return [tuple(row) for row in r]


def write_baseline(path, res):
    """Store the graph as the command line would write it (DOT with the
    default styles and the legend, PNG next to it when Graphviz is
    installed), or as a CSV of edges."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".dot":
        env_config = {e: default_env_style(e) for e in sorted({n.env for n in res.nodes})}
        path.write_text(build_dot(res.nodes, res.edges, env_config, cycle_edges=res.cycles),
                        encoding="utf-8")
        if shutil.which("dot"):
            subprocess.run(["dot", "-Tpng", str(path), "-o", str(path.with_suffix(".png"))],
                           check=False, capture_output=True)
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(result_rows(res))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def check(names=None, write=False, out=print):
    """Run every dataset and mode; return the list of result dicts.
    ``status`` is one of ok, written, diff, missing-baseline, skipped."""
    results = []
    for cfg in load_configs(names):
        for mode, spec in cfg["modes"].items():
            name = cfg["name"]
            res = run_dataset(cfg, mode)
            rec = {"dataset": name, "mode": mode, "status": None,
                   "nodes": None, "edges": None, "added": [], "removed": []}
            if res is None:
                rec["status"] = "skipped"
                rec["note"] = f"input not found: {spec['path']}"
                results.append(rec)
                continue
            rows = result_rows(res)
            rec["nodes"], rec["edges"] = len(res.nodes), len(rows)
            bpath = baseline_path(cfg, mode)
            if write:
                write_baseline(bpath, res)
                rec["status"] = "written"
            elif not bpath.exists():
                rec["status"] = "missing-baseline"
            else:
                base = read_baseline(bpath)
                rec["added"] = sorted(set(rows) - set(base))
                rec["removed"] = sorted(set(base) - set(rows))
                rec["status"] = "ok" if not rec["added"] and not rec["removed"] else "diff"
            results.append(rec)
    _report(results, out)
    return results


def _report(results, out):
    out(f"{'dataset':<14}{'mode':<8}{'nodes':>6}{'edges':>7}  status")
    for r in results:
        line = (f"{r['dataset']:<14}{r['mode']:<8}"
                f"{'' if r['nodes'] is None else r['nodes']:>6}"
                f"{'' if r['edges'] is None else r['edges']:>7}  {r['status']}")
        if r.get("note"):
            line += f"  ({r['note']})"
        out(line)
        for row in r["removed"][:10]:
            out(f"    - {','.join(row)}")
        for row in r["added"][:10]:
            out(f"    + {','.join(row)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="(re)write the stored graphs")
    ap.add_argument("--dataset", action="append", metavar="NAME",
                    help="only this dataset (repeatable)")
    args = ap.parse_args(argv)
    results = check(args.dataset, write=args.write)
    bad = [r for r in results if r["status"] in ("diff", "missing-baseline")]
    if bad:
        print(f"\n{len(bad)} check(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
