"""JSON-in / JSON-out entry points for the web page.

The page calls these either through Pyodide (GitHub Pages build) or
through the local server (``python -m knowtex serve``).  Everything is
plain data (dicts, lists, strings) so it crosses both boundaries.

Functions
---------
expand(files_json, main)        LaTeX project given as {path: text} -> one text
structure(text, fmt)            document class, chapter/section ranges
scan(text, fmt, config_json)    statement kinds found (after range selection)
build(text, fmt, config_json)   edges, cycles, DOT, sections

``config_json`` keys (all optional):
  ranges: [i, ...]                 indices of the ranges (from ``structure``)
                                   to scan; default: the whole text
  mode: "infer" | "manual"         default "infer"
  include: [env, ...]              statement kinds to keep (default: all)
  definition_envs: [env, ...]      definition-like kinds (D4 sources);
                                   default: names matching DEFN_ENV_RX
  ordered: bool                    one document read start to end (default
                                   true); false for several files with no
                                   reading order (D4 ignores position)
  tred: bool                       transitive reduction (default true)
  micro_section: title | null      draw one chapter/section plus its
                                   neighbours ("ghost" nodes)
  removed: [[source, target], ...] edges deleted in the review step
  added: [[source, target, type, location], ...]   edges added by hand
  colors: {env: {shape, border, fill}}
  legend: bool, rankdir: "TB" | "LR"
"""

import json
import re
import traceback

from knowtex.core.constants import DEFN_ENV_RX, H3_MAX_GAP
from knowtex.core.cycles import find_cycles, transitive_reduction
from knowtex.core.data import DependencyEdge
from knowtex.core.dot import build_dot
from knowtex.core.file_expand import expand_from_files
from knowtex.core.formats import detect_format, parse_document
from knowtex.core.structure import (
    assign_sections, detect_doc_class, find_chapter_ranges, find_section_ranges,
)
from knowtex.deps.infer import run_inference
from knowtex.deps.index_registry import build_index_registry
from knowtex.deps.manual import extract_manual_edges
from knowtex.deps.term_extraction import defined_term_strings

_cache = {"key": None, "value": None}


def _fail(e):
    return json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()})


def _fmt(text, fmt):
    return detect_format(text) if fmt in (None, "", "auto") else fmt


def _ranges(text, fmt):
    """(doc_class, range_type, ranges) for a LaTeX text; nothing for Markdown."""
    if fmt != "latex":
        return "article", "section", []
    doc_class = detect_doc_class(text)
    if doc_class == "book":
        return doc_class, "chapter", find_chapter_ranges(text)
    return doc_class, "section", find_section_ranges(text)


def _prepare(text, fmt, cfg):
    """Parse (a selection of) the text once; later calls with the same
    text, format and selection reuse the result."""
    fmt = _fmt(text, fmt)
    sel = cfg.get("ranges")
    key = (text, fmt, tuple(sel) if sel else None)
    if _cache["key"] == key:
        return _cache["value"]

    doc_class, range_type, ranges = _ranges(text, fmt)
    if sel and ranges:
        parts = [text[ranges[i]["start"]:ranges[i]["end"]]
                 for i in sel if 0 <= i < len(ranges)]
        scan_text = "\n\n% [knowtex range separator]\n\n".join(parts)
    else:
        scan_text = text
    used_fmt, nodes, nbi, ltn, proofs, envs = parse_document(scan_text, fmt=fmt)
    # chapter/section of every statement, for the micro view
    if doc_class == "book":
        sec_ranges = find_chapter_ranges(scan_text)
    else:
        sec_ranges = find_section_ranges(scan_text) if fmt == "latex" else []
    section_of = assign_sections(nodes, sec_ranges)
    sections = []
    for n in nodes:
        s = section_of.get(n.label, "(ungrouped)")
        if s not in sections:
            sections.append(s)
    value = {
        "fmt": used_fmt, "text": scan_text, "nodes": nodes, "nbi": nbi,
        "ltn": ltn, "proofs": proofs, "envs": envs,
        "section_of": section_of, "sections": sections,
    }
    _cache.update(key=key, value=value)
    return value


def _node_dict(n, section_of, ghost=False):
    return {
        "label": n.label, "env": n.env, "index": n.index,
        "name": n.display_name,
        "terms": defined_term_strings(n),
        "snippet": n.snippet[:1500],
        "section": section_of.get(n.label, "(ungrouped)"),
        "ghost": ghost,
    }


def expand(files_json, main):
    """Expand a LaTeX project given as JSON {relative path: text}."""
    try:
        files = json.loads(files_json)
        text = expand_from_files(main, files)
        notes = re.findall(r"% \[knowtex\][^\n]*", text)
        return json.dumps({"ok": True, "text": text, "notes": notes,
                           "chars": len(text)})
    except Exception as e:
        return _fail(e)


def structure(text, fmt="auto"):
    """Document class and the chapter/section ranges a user may select."""
    try:
        fmt = _fmt(text, fmt)
        doc_class, range_type, ranges = _ranges(text, fmt)
        return json.dumps({
            "ok": True, "format": fmt, "doc_class": doc_class,
            "range_type": range_type,
            "ranges": [{"index": i, "title": r["title"],
                        "start": r["start"], "end": r["end"]}
                       for i, r in enumerate(ranges)],
        })
    except Exception as e:
        return _fail(e)


def scan(text, fmt="auto", config_json="{}"):
    """Parse the text (or the selected ranges) and describe what was found."""
    try:
        cfg = json.loads(config_json or "{}")
        P = _prepare(text, fmt, cfg)
        counts = {}
        for n in P["nodes"]:
            counts[n.env] = counts.get(n.env, 0) + 1
        env_list = [
            {"env": e, "count": counts.get(e, 0),
             "is_defn": bool(DEFN_ENV_RX.match(e))}
            for e in sorted(P["envs"])
        ]
        return json.dumps({
            "ok": True,
            "format": P["fmt"],
            "detected": detect_format(text),
            "envs": env_list,
            "node_count": len(P["nodes"]),
            "proof_count": len(P["proofs"]),
            "nodes": [_node_dict(n, P["section_of"]) for n in P["nodes"]],
            "sections": P["sections"],
        })
    except Exception as e:
        return _fail(e)


def build(text, fmt="auto", config_json="{}"):
    """Run manual extraction or inference and return edges, cycles and DOT."""
    try:
        cfg = json.loads(config_json or "{}")
        P = _prepare(text, fmt, cfg)
        nodes, ltn, proofs, envs = P["nodes"], P["ltn"], P["proofs"], P["envs"]

        include = set(cfg["include"]) if "include" in cfg else set(envs)
        inc_nodes = [n for n in nodes if n.env in include]
        inc_nbi = {n.index: n for n in inc_nodes}
        inc_ltn = {lbl: n for lbl, n in ltn.items() if n.env in include}

        mode = cfg.get("mode", "infer")
        if mode == "manual":
            edges = extract_manual_edges(inc_nodes, inc_nbi, inc_ltn, proofs)
        else:
            if "definition_envs" in cfg:
                defn = set(cfg["definition_envs"])
            else:  # same default as the CLI
                defn = {e for e in envs if DEFN_ENV_RX.match(e)}
            index_registry = None
            if P["fmt"] == "latex":
                index_registry = build_index_registry(inc_nodes, proofs, P["text"])
            edges = run_inference(inc_nodes, inc_nbi, inc_ltn, proofs,
                                  index_registry=index_registry,
                                  definition_envs=defn,
                                  ordered=bool(cfg.get("ordered", True)))
        visible = set(inc_ltn)
        edges = [e for e in edges if e.source in visible and e.target in visible]

        removed = {tuple(x) for x in cfg.get("removed") or []}
        edges = [e for e in edges if e.key() not in removed]
        have = {e.key() for e in edges}
        for item in cfg.get("added") or []:
            src, tgt = item[0], item[1]
            etype = item[2] if len(item) > 2 else ("manual" if mode == "manual" else "deterministic")
            loc = item[3] if len(item) > 3 else "proof"
            if src != tgt and (src, tgt) not in have and src in visible and tgt in visible:
                edges.append(DependencyEdge(src, tgt, etype, loc, "manual"))
                have.add((src, tgt))

        if cfg.get("tred", True):
            edges = transitive_reduction(edges)
        cycles = find_cycles(edges)

        colors = cfg.get("colors") or {}
        env_config = {e: colors.get(e, {}) for e in sorted(include)}
        micro = cfg.get("micro_section") or None
        dot = build_dot(inc_nodes, edges, env_config, cycle_edges=cycles,
                        section_assignments=P["section_of"],
                        view_mode="micro" if micro else "macro",
                        micro_section=micro,
                        add_legend=bool(cfg.get("legend", True)),
                        rankdir=cfg.get("rankdir"))

        # nodes of the drawing: the section's own, plus ghosts it touches
        if micro:
            own = [n for n in inc_nodes if P["section_of"].get(n.label, "(ungrouped)") == micro]
            own_labels = {n.label for n in own}
            ghost_labels = set()
            for e in edges:
                if e.source in own_labels and e.target not in own_labels:
                    ghost_labels.add(e.target)
                if e.target in own_labels and e.source not in own_labels:
                    ghost_labels.add(e.source)
            drawn = own + [n for n in inc_nodes if n.label in ghost_labels]
            drawn_labels = own_labels | ghost_labels
            out_edges = [e for e in edges if e.source in drawn_labels and e.target in drawn_labels]
        else:
            own_labels = {n.label for n in inc_nodes}
            drawn, out_edges = inc_nodes, edges

        return json.dumps({
            "ok": True,
            "format": P["fmt"],
            "mode": mode,
            "edges": [{"source": e.source, "target": e.target,
                       "type": e.edge_type, "location": e.location,
                       "rule": e.rule, "cycle": e.key() in cycles}
                      for e in out_edges],
            "edge_total": len(edges),
            "cycle_count": len(cycles),
            "dot": dot,
            "nodes": [_node_dict(n, P["section_of"], ghost=n.label not in own_labels)
                      for n in drawn],
            "sections": P["sections"],
            "h3_gap": H3_MAX_GAP,
        })
    except Exception as e:
        return _fail(e)
