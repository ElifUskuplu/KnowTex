"""JSON-in / JSON-out entry points for the web page.

The page calls these either through Pyodide (GitHub Pages build) or
through the local server (``python -m knowtex serve``).  Everything is
plain data (dicts, lists, strings) so it crosses both boundaries.

The page works in steps, and each step does only its own work:

1. ``load`` / ``expand`` store the document and return an id.  Nothing
   is parsed; the text never travels back to the page.
2. ``structure`` lists the chapters/sections (a regex pass, no parse).
3. ``scan`` parses the selected ranges and lists the statement kinds.
   No edges are inferred.
4. ``build`` infers (or reads) the edges and returns the graph.
5. ``snippet`` returns one statement's LaTeX on demand (the node lists
   of ``scan`` and ``build`` carry no snippets).

Functions
---------
load(text, fmt)                 store a pasted or single-file text -> id
expand(files_json, main)        LaTeX project given as {path: text} -> id
structure(doc, fmt)             document class, chapter/section ranges
scan(doc, fmt, config_json)     statement kinds found (after range selection)
build(doc, fmt, config_json)    edges, cycles, dropped edges, DOT, sections
snippet(doc, fmt, label, config_json)   one statement's source

``doc`` is the id returned by ``load``/``expand``; a raw text is accepted
too (it is stored as if ``load`` had been called).

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
  resolve_cycles: bool             infer mode: drop D4 edges closing a cycle
  tred: bool                       transitive reduction (default true)
  micro_section: title | null      draw one chapter/section plus its
                                   neighbours ("ghost" nodes)
  removed: [[source, target], ...] edges deleted in the review step
  added: [[source, target, type, location], ...]   edges added by hand
  colors: {env: {shape, border, fill}}
  legend: bool, rankdir: "TB" | "LR"
"""

import hashlib
import json
import re
import traceback
from collections import OrderedDict

from knowtex.core.constants import DEFN_ENV_RX, H3_MAX_GAP
from knowtex.core.cycles import find_cycles, transitive_reduction
from knowtex.core.data import DependencyEdge
from knowtex.core.dot import build_dot
from knowtex.core.file_expand import expand_from_files
from knowtex.core.formats import detect_format, parse_document
from knowtex.core.structure import (
    assign_sections, detect_doc_class, find_chapter_ranges, find_section_ranges,
)
from knowtex.deps.infer import run_inference, resolve_cycles
from knowtex.deps.index_registry import build_index_registry
from knowtex.deps.manual import extract_manual_edges
from knowtex.deps.term_extraction import WordCache, defined_term_strings

MAX_DOCS = 3          # documents kept in memory (least recently used dropped)
MAX_EDGE_CACHE = 16   # inference results kept per parse


class Document:
    """A loaded text with everything computed from it so far."""

    def __init__(self, doc_id, text, fmt):
        self.id = doc_id
        self.text = text
        self.fmt_given = fmt if fmt in ("latex", "markdown") else "auto"
        self._fmt = None
        self._structure = None
        self.parses = OrderedDict()    # selection key -> Parse

    @property
    def fmt(self):
        if self._fmt is None:
            self._fmt = self.fmt_given if self.fmt_given != "auto" else detect_format(self.text)
        return self._fmt

    def structure(self):
        """(doc_class, range_type, ranges); a regex pass over the text."""
        if self._structure is None:
            if self.fmt != "latex":
                self._structure = ("article", "section", [])
            else:
                doc_class = detect_doc_class(self.text)
                if doc_class == "book":
                    self._structure = (doc_class, "chapter", find_chapter_ranges(self.text))
                else:
                    self._structure = (doc_class, "section", find_section_ranges(self.text))
        return self._structure

    def parse(self, selection):
        """The parse of the selected ranges (``None`` = whole text)."""
        key = tuple(selection) if selection else None
        P = self.parses.get(key)
        if P is None:
            P = Parse(self, key)
            self.parses[key] = P
            while len(self.parses) > MAX_DOCS:
                self.parses.popitem(last=False)
        else:
            self.parses.move_to_end(key)
        return P


class Parse:
    """Statements and proofs of (a selection of) a document, with the
    caches every later step builds on: words and stems of the statements
    and the edges each configuration produced."""

    def __init__(self, doc, key):
        doc_class, range_type, ranges = doc.structure()
        if key and ranges:
            parts = [doc.text[ranges[i]["start"]:ranges[i]["end"]]
                     for i in key if 0 <= i < len(ranges)]
            text = "\n\n% [knowtex range separator]\n\n".join(parts)
        else:
            text = doc.text
        self.text = text
        (self.fmt, self.nodes, self.nbi, self.ltn,
         self.proofs, self.envs) = parse_document(text, fmt=doc.fmt)
        # chapter/section of every statement, for the micro view
        if doc_class == "book":
            sec_ranges = find_chapter_ranges(text)
        else:
            sec_ranges = find_section_ranges(text) if self.fmt == "latex" else []
        self.section_of = assign_sections(self.nodes, sec_ranges)
        self.sections = []
        for n in self.nodes:
            s = self.section_of.get(n.label, "(ungrouped)")
            if s not in self.sections:
                self.sections.append(s)
        self.words = WordCache()
        self.index_registry = None
        self.edge_cache = OrderedDict()   # config key -> (edges, dropped)

    def registry(self):
        if self.index_registry is None and self.fmt == "latex":
            self.index_registry = build_index_registry(self.nodes, self.proofs, self.text)
        return self.index_registry

    def cached(self, key, compute):
        if key in self.edge_cache:
            self.edge_cache.move_to_end(key)
            return self.edge_cache[key]
        value = self.edge_cache[key] = compute()
        while len(self.edge_cache) > MAX_EDGE_CACHE:
            self.edge_cache.popitem(last=False)
        return value


_docs = OrderedDict()      # id -> Document


def _store(text, fmt):
    doc_id = "doc:" + hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    doc = _docs.get(doc_id)
    if doc is None or doc.fmt_given != (fmt if fmt in ("latex", "markdown") else "auto"):
        doc = Document(doc_id, text, fmt)
        _docs[doc_id] = doc
    _docs.move_to_end(doc_id)
    while len(_docs) > MAX_DOCS:
        _docs.popitem(last=False)
    return doc


def _doc(ref, fmt):
    """The Document for an id from ``load``/``expand``, or for a raw text."""
    doc = _docs.get(ref) if isinstance(ref, str) and ref.startswith("doc:") else None
    if doc is not None:
        _docs.move_to_end(ref)
        return doc
    if isinstance(ref, str) and ref.startswith("doc:") and len(ref) == 20 and " " not in ref:
        raise KeyError(f"unknown document {ref}; load it again")
    return _store(ref, fmt)


def _fail(e):
    return json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()})


def _node_dict(n, section_of, ghost=False):
    return {
        "label": n.label, "env": n.env, "index": n.index,
        "name": n.display_name,
        "terms": defined_term_strings(n),
        "section": section_of.get(n.label, "(ungrouped)"),
        "ghost": ghost,
    }


def _edge_dict(e, cycles=None):
    d = {"source": e.source, "target": e.target, "type": e.edge_type,
         "location": e.location, "rule": e.rule}
    if cycles is not None:
        d["cycle"] = e.key() in cycles
    return d


# ---------------------------------------------------------------- 1. load

def load(text, fmt="auto"):
    """Store a pasted or single-file text.  Nothing is parsed."""
    try:
        doc = _store(text, fmt)
        return json.dumps({"ok": True, "id": doc.id, "format": doc.fmt_given,
                           "chars": len(text)})
    except Exception as e:
        return _fail(e)


def expand(files_json, main):
    """Expand a LaTeX project given as JSON {relative path: text} and
    store the result.  Only ``\\input``-like commands are resolved; the
    text is not parsed and is not returned."""
    try:
        files = json.loads(files_json)
        text = expand_from_files(main, files)
        notes = re.findall(r"% \[knowtex\][^\n]*", text)
        doc = _store(text, "latex")
        return json.dumps({"ok": True, "id": doc.id, "format": "latex",
                           "notes": notes, "chars": len(text)})
    except Exception as e:
        return _fail(e)


# ---------------------------------------------------------------- 2. structure

def structure(doc, fmt="auto"):
    """Document class and the chapter/section ranges a user may select."""
    try:
        D = _doc(doc, fmt)
        doc_class, range_type, ranges = D.structure()
        return json.dumps({
            "ok": True, "id": D.id, "format": D.fmt, "doc_class": doc_class,
            "range_type": range_type,
            "ranges": [{"index": i, "title": r["title"],
                        "start": r["start"], "end": r["end"]}
                       for i, r in enumerate(ranges)],
        })
    except Exception as e:
        return _fail(e)


# ---------------------------------------------------------------- 3. scan

def scan(doc, fmt="auto", config_json="{}"):
    """Parse the text (or the selected ranges) and describe what was found.
    No edges are inferred here."""
    try:
        cfg = json.loads(config_json or "{}")
        D = _doc(doc, fmt)
        P = D.parse(cfg.get("ranges"))
        counts = {}
        for n in P.nodes:
            counts[n.env] = counts.get(n.env, 0) + 1
        env_list = [
            {"env": e, "count": counts.get(e, 0),
             "is_defn": bool(DEFN_ENV_RX.match(e))}
            for e in sorted(P.envs)
        ]
        return json.dumps({
            "ok": True,
            "id": D.id,
            "format": P.fmt,
            "detected": D.fmt,
            "envs": env_list,
            "node_count": len(P.nodes),
            "proof_count": len(P.proofs),
            "nodes": [_node_dict(n, P.section_of) for n in P.nodes],
            "sections": P.sections,
        })
    except Exception as e:
        return _fail(e)


def snippet(doc, fmt="auto", label="", config_json="{}"):
    """The LaTeX (or Markdown) source of one statement."""
    try:
        cfg = json.loads(config_json or "{}")
        D = _doc(doc, fmt)
        P = D.parse(cfg.get("ranges"))
        n = P.ltn.get(label)
        if n is None:
            return json.dumps({"ok": False, "error": f"unknown label {label!r}"})
        return json.dumps({"ok": True, "label": label, "snippet": n.snippet[:4000],
                           "truncated": len(n.snippet) > 4000})
    except Exception as e:
        return _fail(e)


# ---------------------------------------------------------------- 4. build

def _infer(P, cfg):
    """Raw edges of a configuration (before the user's edits): cached per
    parse, so toggling display options or editing edges does not rerun
    the rules."""
    include = set(cfg["include"]) if "include" in cfg else set(P.envs)
    mode = cfg.get("mode", "infer")
    if "definition_envs" in cfg:
        defn = set(cfg["definition_envs"])
    else:  # same default as the CLI
        defn = {e for e in P.envs if DEFN_ENV_RX.match(e)}
    ordered = bool(cfg.get("ordered", True))
    key = ("raw", mode, frozenset(include), frozenset(defn) if mode == "infer" else None, ordered)

    def compute():
        inc_nodes = [n for n in P.nodes if n.env in include]
        inc_nbi = {n.index: n for n in inc_nodes}
        inc_ltn = {lbl: n for lbl, n in P.ltn.items() if n.env in include}
        if mode == "manual":
            edges = extract_manual_edges(inc_nodes, inc_nbi, inc_ltn, P.proofs)
        else:
            edges = run_inference(inc_nodes, inc_nbi, inc_ltn, P.proofs,
                                  index_registry=P.registry(),
                                  definition_envs=defn, ordered=ordered,
                                  word_cache=P.words)
        visible = set(inc_ltn)
        return [e for e in edges if e.source in visible and e.target in visible], inc_nodes

    return P.cached(key, compute), include, mode


def build(doc, fmt="auto", config_json="{}"):
    """Run manual extraction or inference and return edges, cycles and DOT.

    In infer mode the D4 edges that close a cycle are resolved first
    (``resolve_cycles``; ``resolve_cycles: false`` in the config keeps
    them); the dropped edges are returned as ``dropped_edges``.
    """
    try:
        cfg = json.loads(config_json or "{}")
        D = _doc(doc, fmt)
        P = D.parse(cfg.get("ranges"))
        (raw_edges, inc_nodes), include, mode = _infer(P, cfg)
        visible = {n.label for n in inc_nodes}

        removed = {tuple(x) for x in cfg.get("removed") or []}
        added = tuple(tuple(x) for x in cfg.get("added") or [])
        resolve = mode == "infer" and cfg.get("resolve_cycles", True)

        def edited():
            edges = [e for e in raw_edges if e.key() not in removed]
            have = {e.key() for e in edges}
            for item in added:
                src, tgt = item[0], item[1]
                etype = item[2] if len(item) > 2 else ("manual" if mode == "manual" else "deterministic")
                loc = item[3] if len(item) > 3 else "proof"
                if src != tgt and (src, tgt) not in have and src in visible and tgt in visible:
                    edges.append(DependencyEdge(src, tgt, etype, loc, "manual"))
                    have.add((src, tgt))
            dropped = []
            if resolve:
                edges, dropped = resolve_cycles(edges, inc_nodes, word_cache=P.words)
            return edges, dropped

        key = ("edited", mode, frozenset(include),
               frozenset(cfg.get("definition_envs", ())) if "definition_envs" in cfg else None,
               bool(cfg.get("ordered", True)), frozenset(removed), added, resolve)
        edges, dropped = P.cached(key, edited)

        if cfg.get("tred", True):
            edges = transitive_reduction(edges)
        cycles = find_cycles(edges)

        colors = cfg.get("colors") or {}
        env_config = {e: colors.get(e, {}) for e in sorted(include)}
        micro = cfg.get("micro_section") or None
        dot = build_dot(inc_nodes, edges, env_config, cycle_edges=cycles,
                        section_assignments=P.section_of,
                        view_mode="micro" if micro else "macro",
                        micro_section=micro,
                        add_legend=bool(cfg.get("legend", True)),
                        rankdir=cfg.get("rankdir"))

        # nodes of the drawing: the section's own, plus ghosts it touches
        if micro:
            own = [n for n in inc_nodes if P.section_of.get(n.label, "(ungrouped)") == micro]
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
            own_labels = visible
            drawn, out_edges = inc_nodes, edges

        return json.dumps({
            "ok": True,
            "id": D.id,
            "format": P.fmt,
            "mode": mode,
            "edges": [_edge_dict(e, cycles) for e in out_edges],
            "edge_total": len(edges),
            "cycle_count": len(cycles),
            "dropped_count": len(dropped),
            "dropped_edges": [_edge_dict(e) for e in dropped],
            "dot": dot,
            "nodes": [_node_dict(n, P.section_of, ghost=n.label not in own_labels)
                      for n in drawn],
            "sections": P.sections,
            "h3_gap": H3_MAX_GAP,
        })
    except Exception as e:
        return _fail(e)
