"""Command-line interface: infer a dependency graph from the terminal.

Usage:
    python -m knowtex.cli notes.md                 # print edges
    python -m knowtex.cli notes.tex --dot out.dot  # write DOT
    python -m knowtex.cli notes.md --json out.json   # nodes and edges as JSON
    python -m knowtex.cli glossary_folder/         # Markdown files as one glossary
    python -m knowtex.cli main.tex --config run.json   # options of a page run
    cat notes.md | python -m knowtex.cli -         # read stdin

LaTeX projects with \\input/\\include are expanded from the main file.
The options that change the edges (``--mode``, ``--include-env``,
``--definition-env``, ``--unordered``, ``--keep-cycles``, ``--no-tred``)
are the keys of the web page's configuration; ``--config FILE`` reads the
same keys from a JSON file, and a flag given on the command line wins
over the file.  See ``knowtex/pipeline.py``.
"""

import argparse
import json
import sys
from pathlib import Path

from knowtex.core.constants import default_env_style
from knowtex.core.dot import build_dot
from knowtex.pipeline import PipelineConfig, load_input, run_pipeline


def build_config(args, is_collection=False):
    """The PipelineConfig of a parsed command line: the config file first,
    then the flags, then the defaults.  A folder of files has no reading
    order, so it is ``ordered=False`` unless the config file or a flag
    says otherwise."""
    cfg = {}
    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.mode is not None:
        cfg["mode"] = args.mode
    if args.include_env:
        cfg["include"] = list(args.include_env)
    if args.definition_env:
        cfg["definition_envs"] = list(args.definition_env)
    if args.unordered:
        cfg["ordered"] = False
    elif "ordered" not in cfg and is_collection:
        cfg["ordered"] = False
    if args.disable_rule:
        cfg["disabled_rules"] = list(args.disable_rule)
    if args.keep_cycles:
        cfg["resolve_cycles"] = False
    if args.no_tred:
        cfg["tred"] = False
    return PipelineConfig.from_dict(cfg)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="knowtex", description=__doc__.split("\n\n")[0])
    ap.add_argument("path", help="input file, folder of Markdown files, or - for stdin")
    ap.add_argument("--format", choices=["auto", "latex", "markdown"], default="auto")
    ap.add_argument("--config", metavar="FILE",
                    help="JSON file with the page's configuration keys (mode, include, "
                         "definition_envs, ordered, resolve_cycles, tred); flags override it")
    ap.add_argument("--mode", choices=["infer", "manual"], default=None,
                    help="infer (default) or manual (\\uses{} annotations only)")
    ap.add_argument("--include-env", action="append", default=None, metavar="ENV",
                    help="statement kind to keep (repeatable); default: all kinds found")
    ap.add_argument("--definition-env", action="append", default=None, metavar="ENV",
                    help="environment treated as definition-like (repeatable); "
                         "default: names matching definition/notation/axiom/...")
    ap.add_argument("--unordered", action="store_true",
                    help="no reading order: D4 may link a definition to any statement "
                         "(the default for a folder of Markdown files)")
    ap.add_argument("--disable-rule", action="append", default=None, metavar="RULE",
                    help="switch a rule off (D1, D2, D4, H2, H3, H4; repeatable), "
                         "for ablation experiments")
    ap.add_argument("--no-tred", action="store_true",
                    help="skip transitive reduction (applied by default)")
    ap.add_argument("--keep-cycles", action="store_true",
                    help="keep D4 term-match edges that close a cycle (by default "
                         "the weakest of them are dropped until only cycles made "
                         "of explicit references remain)")
    ap.add_argument("--dot", metavar="FILE", help="write Graphviz DOT")
    ap.add_argument("--json", metavar="FILE", help="write nodes and edges as JSON")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    text, fmt, is_collection = load_input(args.path, args.format)
    config = build_config(args, is_collection)
    result = run_pipeline(text, fmt, config)
    edges, cycles = result.edges, result.cycles

    if not args.quiet:
        print(f"format: {result.fmt}   statements: {len(result.nodes)}"
              f"{'' if len(result.nodes) == len(result.all_nodes) else f' of {len(result.all_nodes)}'}"
              f"   proofs: {len(result.proofs)}   edges: {len(edges)}"
              f"   cycle edges: {len(cycles)}"
              f"{f'   dropped by cycle resolution: {len(result.dropped)}' if result.dropped else ''}",
              file=sys.stderr)
        for e in edges:
            flag = " (cycle)" if e.key() in cycles else ""
            print(f"{e.rule:3} {e.source} -> {e.target}{flag}")

    if args.dot:
        env_config = {e: default_env_style(e) for e in sorted({n.env for n in result.nodes})}
        Path(args.dot).write_text(
            build_dot(result.nodes, edges, env_config, cycle_edges=cycles), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
