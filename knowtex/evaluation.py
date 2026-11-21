"""Evaluation helpers for the article's datasets.

Runs the pipeline on a dataset described by a config dict (see
``tests/datasets.py`` for the four case studies), loads its gold graph
and computes the metrics of the article: precision, recall and F1 on
``(source, target)`` pairs, the path-based variants (an extra edge counts
as justified when the gold graph has a path from its source to its
target; a missed edge as recovered when the inferred graph has such a
path), and the agreement of edge styles.  ``tests/regression.py`` and
``tests/test_report.py`` build on it.

A config has ``name``, ``modes`` (per mode: ``path``, ``format``, the
pipeline ``config`` keys) and a ``gold`` section that looks like one of:

    {"type": "manual", "mode": "manual", "aliases": {"gold label": "inferred label"}}
    {"type": "blueprint_html", "path": "…/Dependency-graph.html", "aliases": {…}}
    {"type": "chicago_hyperlinks"}

``aliases`` rename gold labels to the labels the inferred graph uses
(the article's "normalized" numbers).  Chicago maps the other way: the
inferred ``definition:<slug>`` labels are mapped to the ground truth's
``def:<slug>`` with the benchmark's own mapper.
"""

import html
import importlib.util
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from knowtex.pipeline import PipelineConfig, load_input, run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# configs and runs
# ---------------------------------------------------------------------------

def dataset_available(cfg, mode="infer"):
    return (PROJECT_ROOT / cfg["modes"][mode]["path"]).exists()


def run_dataset(cfg, mode, overrides=None):
    """Run one dataset in one mode; *overrides* are extra PipelineConfig
    keys (for example ``{"disabled_rules": ["H3"]}``).  Returns a
    PipelineResult, or ``None`` when the input is not there."""
    spec = cfg["modes"][mode]
    path = PROJECT_ROOT / spec["path"]
    if not path.exists():
        return None
    text, fmt, _ = load_input(str(path), spec.get("format", "auto"))
    d = dict(spec.get("config", {}))
    d.update(overrides or {})
    return run_pipeline(text, fmt, PipelineConfig.from_dict(d))


# ---------------------------------------------------------------------------
# edges, styles, DOT and Blueprint files
# ---------------------------------------------------------------------------

def edge_style(edge):
    """The DOT style the page gives an edge."""
    if edge.edge_type == "heuristic":
        return "dotted"
    return "solid" if edge.location == "proof" else "dashed"


_DOT_EDGE_RX = re.compile(
    r'("([^"]+)"|([\w.:\-]+))\s*->\s*("([^"]+)"|([\w.:\-]+))\s*(\[([^\]]*)\])?\s*;')


def dot_edges(path):
    """``(source, target, rule, style)`` tuples of a DOT file written by
    KnowTeX (legend left out).  The rule is read from the edge's tooltip
    (``"D1: a -> b"``); an edge without one gets ``?``."""
    text = Path(path).read_text(encoding="utf-8")
    out = []
    for m in _DOT_EDGE_RX.finditer(text):
        a = m.group(2) or m.group(3)
        b = m.group(5) or m.group(6)
        if "__legend__" in (a, b):
            continue
        attrs = m.group(8) or ""
        style = re.search(r"style=\"?(\w+)", attrs)
        tip = re.search(r'tooltip="([^":]*):', attrs)
        out.append((a, b, tip.group(1) if tip else "?", style.group(1) if style else "solid"))
    return out


_SVG_EDGE_RX = re.compile(r'<g id="[^"]*" class="edge">(.*?)</g>', re.S)
_SVG_TITLE_RX = re.compile(r"<title>(.*?)</title>", re.S)


def blueprint_edges_from_text(svg_text):
    """``(source, target, style)`` tuples of a Lean Blueprint dependency
    graph page: Graphviz SVG with ``<g class="edge"><title>a->b</title>``
    and ``stroke-dasharray`` on dashed (statement-level) edges."""
    out = []
    for block in _SVG_EDGE_RX.findall(svg_text):
        m = _SVG_TITLE_RX.search(block)
        if not m:
            continue
        title = html.unescape(m.group(1)).strip()
        if "->" not in title:
            continue
        a, b = (x.strip() for x in title.split("->", 1))
        out.append((a, b, "dashed" if "stroke-dasharray" in block else "solid"))
    return out


def blueprint_edges(path):
    return blueprint_edges_from_text(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# gold standards
# ---------------------------------------------------------------------------

@dataclass
class Gold:
    """A gold graph in the label space of the inferred graph."""
    name: str
    kind: str
    pairs: set                          # {(source, target)}
    styles: dict = field(default_factory=dict)   # (source, target) -> style
    map_pred: object = None             # function applied to inferred labels (Chicago)
    note: str = ""

    def pred_pairs(self, result):
        """``(source, target)`` pairs of a PipelineResult in the gold's label space."""
        f = self.map_pred or (lambda x: x)
        return {(f(e.source), f(e.target)) for e in result.edges}

    def pred_styles(self, result):
        f = self.map_pred or (lambda x: x)
        return {(f(e.source), f(e.target)): edge_style(e) for e in result.edges}


def _apply_aliases(triples, aliases):
    a = aliases or {}
    return [(a.get(s, s), a.get(t, t), st) for s, t, st in triples]


def _chicago_module(cfg):
    path = PROJECT_ROOT / "chicago_notes" / "chicago_benchmark.py"
    spec = importlib.util.spec_from_file_location("chicago_benchmark", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_gold(cfg):
    """The gold graph a config describes, or ``None`` if it has none or
    its input is missing."""
    spec = cfg.get("gold")
    if not spec:
        return None
    kind = spec["type"]
    if kind == "manual":
        res = run_dataset(cfg, spec.get("mode", "manual"))
        if res is None:
            return None
        triples = _apply_aliases([(e.source, e.target, edge_style(e)) for e in res.edges],
                                 spec.get("aliases"))
        note = f"manual mode on {cfg['modes'][spec.get('mode', 'manual')]['path']}"
    elif kind == "blueprint_html":
        path = PROJECT_ROOT / spec["path"]
        if not path.exists():
            return None
        triples = _apply_aliases(blueprint_edges(path), spec.get("aliases"))
        note = f"Lean Blueprint graph from {spec['path']}"
    elif kind == "chicago_hyperlinks":
        if not dataset_available(cfg):
            return None
        mod = _chicago_module(cfg)
        defs = mod.load_all_definitions()
        gt = mod.build_ground_truth(defs)
        return Gold(cfg["name"], kind, set(gt), {}, mod.gt_label_mapper(defs),
                    "hyperlinks of the MathGloss Chicago files")
    else:
        raise ValueError(f"unknown gold type {kind!r}")
    pairs = {(s, t) for s, t, _ in triples}
    styles = {(s, t): st for s, t, st in triples}
    return Gold(cfg["name"], kind, pairs, styles, None, note)


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def reachability(pairs):
    """A function ``reach(a, b)``: is there a directed path a -> … -> b
    (length >= 1) in the graph with these edges?"""
    adj = defaultdict(set)
    for s, t in pairs:
        adj[s].add(t)
    cache = {}

    def descendants(a):
        if a not in cache:
            seen, dq = set(), deque([a])
            while dq:
                x = dq.popleft()
                for y in adj.get(x, ()):
                    if y not in seen:
                        seen.add(y)
                        dq.append(y)
            cache[a] = seen
        return cache[a]

    return lambda a, b: b in descendants(a)


def compare(pred_pairs, gold_pairs, pred_styles=None, gold_styles=None):
    """Edge-level and path-based metrics of *pred_pairs* against *gold_pairs*.

    Returns a dict with tp, fp, fn, precision, recall, f1,
    path_justified (extra edges with a gold path), path_precision,
    path_recovered (missed gold edges with a predicted path), path_recall,
    and, when styles are given, style_matches / style_total / style_accuracy
    over the common edges.
    """
    pred, gold = set(pred_pairs), set(gold_pairs)
    tp, fp, fn = pred & gold, pred - gold, gold - pred
    p, r, f = prf(len(tp), len(fp), len(fn))
    out = {"predicted": len(pred), "gold": len(gold),
           "tp": len(tp), "fp": len(fp), "fn": len(fn),
           "precision": p, "recall": r, "f1": f}
    in_gold = reachability(gold)
    in_pred = reachability(pred)
    justified = {e for e in fp if in_gold(*e)}
    recovered = {e for e in fn if in_pred(*e)}
    out["path_justified"] = len(justified)
    out["path_precision"] = (len(tp) + len(justified)) / len(pred) if pred else 0.0
    out["path_recovered"] = len(recovered)
    out["path_recall"] = (len(tp) + len(recovered)) / len(gold) if gold else 0.0
    out["truly_spurious"] = len(fp) - len(justified)
    out["extra_edges"] = sorted(fp)
    out["missed_edges"] = sorted(fn)
    out["justified_edges"] = sorted(justified)
    if pred_styles is not None and gold_styles is not None:
        common = [e for e in tp if e in pred_styles and e in gold_styles]
        matches = sum(1 for e in common if pred_styles[e] == gold_styles[e])
        out["style_total"] = len(common)
        out["style_matches"] = matches
        out["style_accuracy"] = matches / len(common) if common else 0.0
    return out


def evaluate(result, gold):
    """``compare`` of a PipelineResult against a Gold."""
    return compare(gold.pred_pairs(result), gold.pairs,
                   gold.pred_styles(result), gold.styles or None)
