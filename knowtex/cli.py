"""Command-line interface: infer a dependency graph from the terminal.

Usage:
    python -m knowtex.cli notes.md                 # print edges
    python -m knowtex.cli notes.tex --dot out.dot  # write DOT
    python -m knowtex.cli notes.md --json out.json   # nodes and edges as JSON
    cat notes.md | python -m knowtex.cli -         # read stdin

LaTeX projects with \\input/\\include are expanded from the main file.
"""

import argparse
import json
import sys
from pathlib import Path

from knowtex.core.constants import DEFN_ENV_RX
from knowtex.core.cycles import find_cycles, transitive_reduction
from knowtex.core.dot import build_dot
from knowtex.core.formats import FORMAT_BY_SUFFIX, parse_document
from knowtex.deps.index_registry import build_index_registry
from knowtex.deps.infer import run_inference
from knowtex.deps.manual import extract_manual_edges


def load_text(path, fmt):
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if fmt == "latex" and p.suffix.lower() in (".tex", ".ltx"):
        from knowtex.core.file_expand import load_and_expand
        return load_and_expand(str(p))
    return p.read_text(encoding="utf-8", errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="knowtex", description=__doc__.split("\n\n")[0])
    ap.add_argument("path", help="input file, or - for stdin")
    ap.add_argument("--format", choices=["auto", "latex", "markdown"], default="auto")
    ap.add_argument("--mode", choices=["infer", "manual"], default="infer")
    ap.add_argument("--definition-env", action="append", default=None,
                    help="environment treated as definition-like (repeatable); "
                         "default: names matching definition/notation/axiom/...")
    ap.add_argument("--no-tred", action="store_true",
                    help="skip transitive reduction (applied by default)")
    ap.add_argument("--dot", metavar="FILE", help="write Graphviz DOT")
    ap.add_argument("--json", metavar="FILE", help="write nodes and edges as JSON")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    fmt = args.format
    if fmt == "auto" and args.path != "-":
        # A known extension decides the format (and whether to expand
        # \\input); otherwise the content is sniffed by parse_document.
        fmt = FORMAT_BY_SUFFIX.get(Path(args.path).suffix.lower(), "auto")
    text = load_text(args.path, fmt)
    used_fmt, nodes, nbi, ltn, proofs, envs = parse_document(text, fmt=None if fmt == "auto" else fmt)

    if args.mode == "manual":
        edges = extract_manual_edges(nodes, nbi, ltn, proofs)
    else:
        defn = set(args.definition_env) if args.definition_env else {
            e for e in envs if DEFN_ENV_RX.match(e)}
        registry = build_index_registry(nodes, proofs, text) if used_fmt == "latex" else None
        edges = run_inference(nodes, nbi, ltn, proofs, index_registry=registry,
                              definition_envs=defn)
    if not args.no_tred:
        edges = transitive_reduction(edges)
    cycles = find_cycles(edges)

    if not args.quiet:
        print(f"format: {used_fmt}   statements: {len(nodes)}   proofs: {len(proofs)}   "
              f"edges: {len(edges)}   cycle edges: {len(cycles)}", file=sys.stderr)
        for e in edges:
            flag = " (cycle)" if e.key() in cycles else ""
            print(f"{e.rule:3} {e.source} -> {e.target}{flag}")

    if args.dot:
        env_config = {e: {} for e in sorted(envs)}
        Path(args.dot).write_text(
            build_dot(nodes, edges, env_config, cycle_edges=cycles), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "format": used_fmt,
            "nodes": [{"label": n.label, "env": n.env, "index": n.index,
                       "name": n.display_name} for n in nodes],
            "edges": [{"source": e.source, "target": e.target, "rule": e.rule,
                       "type": e.edge_type, "location": e.location} for e in edges],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
