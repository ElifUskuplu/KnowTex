"""Headless pipeline: text in, statements and edges out.

This is the one place where the steps of a run are put together:

    parse_document -> select the statement kinds -> rules (or \\uses{})
        -> cycle resolution -> transitive reduction

The command line (``knowtex/cli.py``), the web page (``knowtex/webapi.py``)
and the scripts (``tests/regression.py``, ``chicago_notes/``) all call the functions below,
so a graph built on the page can be rebuilt from the terminal with the
same configuration and gives the same edges.

``PipelineConfig`` holds the options that change the edges.  Its keys are
the same as the ``config_json`` keys of the web page (``mode``,
``include``, ``definition_envs``, ``ordered``, ``resolve_cycles``,
``tred``); the page's display and editing keys (``ranges``, ``removed``,
``added``, ``colors``, ...) are not part of a pipeline run and are
ignored by ``PipelineConfig.from_dict``.

    >>> from knowtex.pipeline import PipelineConfig, run_pipeline
    >>> cfg = PipelineConfig(include={"defn", "thm", "lemma", "cor"})
    >>> result = run_pipeline(open("main.tex").read(), "latex", cfg)
    >>> for source, target, rule, edge_type, location in result.edge_rows():
    ...     print(rule, source, "->", target)
"""

from dataclasses import dataclass, field
import json
import os
import sys

from knowtex.core.constants import DEFN_ENV_RX
from knowtex.core.cycles import find_cycles, transitive_reduction
from knowtex.core.formats import (
    FORMAT_BY_SUFFIX, markdown_files, parse_document, read_markdown_files,
)
from knowtex.deps.index_registry import build_index_registry
from knowtex.deps.infer import run_inference, resolve_cycles
from knowtex.deps.manual import extract_manual_edges

MODES = ("infer", "manual")

#: config keys that change the edges (read by ``PipelineConfig``)
CONFIG_KEYS = ("mode", "include", "definition_envs", "ordered", "resolve_cycles", "tred",
               "disabled_rules")
#: config keys of the web page that only concern the drawing or the review
#: step; accepted and ignored here so a page config can be passed as is
PAGE_ONLY_KEYS = ("ranges", "removed", "added", "colors", "legend", "rankdir",
                  "micro_section")


def default_definition_envs(envs):
    """The definition-like kinds among *envs* (names matching DEFN_ENV_RX):
    the default D4 sources of the command line and the page."""
    return frozenset(e for e in envs if DEFN_ENV_RX.match(e))


@dataclass(frozen=True)
class PipelineConfig:
    """The options of a run that change the edges.

    include          statement kinds (environment names) kept; ``None`` = all
    definition_envs  definition-like kinds, the D4 sources; ``None`` = the
                     kinds matching DEFN_ENV_RX among those found
    ordered          one document read start to end (D4 links a definition
                     only to later statements); ``False`` for a set of
                     files with no reading order
    resolve_cycles   infer mode: drop the D4 edges that close a cycle,
                     weakest evidence first
    tred             transitive reduction of the final edge set
    disabled_rules   rules switched off (ablation experiments only)
    """
    mode: str = "infer"
    include: frozenset | None = None
    definition_envs: frozenset | None = None
    ordered: bool = True
    resolve_cycles: bool = True
    tred: bool = True
    disabled_rules: frozenset | None = None

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {self.mode!r}")
        for name in ("include", "definition_envs", "disabled_rules"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, frozenset):
                object.__setattr__(self, name, frozenset(value))

    @classmethod
    def from_dict(cls, d, strict=True):
        """A config from a dict with the web page's keys.  Unknown keys
        raise ``KeyError`` when *strict* (a typo in a config file should
        not silently run the defaults)."""
        d = dict(d or {})
        unknown = set(d) - set(CONFIG_KEYS) - set(PAGE_ONLY_KEYS)
        if unknown and strict:
            raise KeyError(f"unknown config key(s): {', '.join(sorted(unknown))}; "
                           f"expected {', '.join(CONFIG_KEYS)}")
        kw = {}
        for k in CONFIG_KEYS:
            if k in d and d[k] is not None:
                kw[k] = d[k]
        for k in ("ordered", "resolve_cycles", "tred"):
            if k in kw:
                kw[k] = bool(kw[k])
        return cls(**kw)

    @classmethod
    def from_json(cls, text, strict=True):
        return cls.from_dict(json.loads(text or "{}"), strict=strict)

    def to_dict(self):
        """JSON-ready dict (sets become sorted lists)."""
        return {
            "mode": self.mode,
            "include": sorted(self.include) if self.include is not None else None,
            "definition_envs": (sorted(self.definition_envs)
                                if self.definition_envs is not None else None),
            "ordered": self.ordered,
            "resolve_cycles": self.resolve_cycles,
            "tred": self.tred,
            "disabled_rules": (sorted(self.disabled_rules)
                               if self.disabled_rules is not None else None),
        }

    def replace(self, **changes):
        from dataclasses import replace
        return replace(self, **changes)


def select_nodes(nodes, label_to_node, include):
    """The statements of the selected kinds, with the index and label maps
    the rules need.  ``include=None`` keeps every statement."""
    if include is None:
        inc_nodes = list(nodes)
        inc_ltn = dict(label_to_node)
    else:
        inc_nodes = [n for n in nodes if n.env in include]
        inc_ltn = {lbl: n for lbl, n in label_to_node.items() if n.env in include}
    return inc_nodes, {n.index: n for n in inc_nodes}, inc_ltn


def raw_edges(nodes, node_by_index, label_to_node, proofs, config, envs,
              index_registry=None, word_cache=None):
    """The edges of the rules (infer mode) or of ``\\uses{}`` (manual mode)
    on the selected statements, before cycle resolution and transitive
    reduction.  Edges touching an unselected statement are left out.

    *envs* are all the kinds found in the document; the default D4
    sources are taken from them, not only from the selected kinds, so a
    selection never changes which kinds count as definitions.
    """
    if config.mode == "manual":
        edges = extract_manual_edges(nodes, node_by_index, label_to_node, proofs)
    else:
        defn = (config.definition_envs if config.definition_envs is not None
                else default_definition_envs(envs))
        edges = run_inference(nodes, node_by_index, label_to_node, proofs,
                              index_registry=index_registry,
                              definition_envs=set(defn), ordered=config.ordered,
                              word_cache=word_cache,
                              disabled_rules=config.disabled_rules)
    visible = set(label_to_node)
    return [e for e in edges if e.source in visible and e.target in visible]


def finish_edges(edges, nodes, config, word_cache=None):
    """Cycle resolution (infer mode, when enabled) and transitive
    reduction.  Returns ``(edges, dropped)``."""
    dropped = []
    if config.mode == "infer" and config.resolve_cycles:
        edges, dropped = resolve_cycles(edges, nodes, word_cache=word_cache)
    if config.tred:
        edges = transitive_reduction(edges)
    return edges, dropped


@dataclass
class PipelineResult:
    """What one run produced."""
    fmt: str                       # "latex" or "markdown"
    nodes: list                    # the selected statements (NodeInfo)
    all_nodes: list                # every statement found
    proofs: list                   # every proof found (ProofInfo)
    envs: set                      # every statement kind found
    edges: list                    # final edges (DependencyEdge)
    dropped: list                  # D4 edges removed by the cycle resolution
    cycles: set                    # (source, target) keys of edges on a cycle
    config: PipelineConfig
    text: str = field(default="", repr=False)

    def edge_rows(self):
        """Sorted ``(source, target, rule, type, location)`` tuples: the
        format of the regression baselines (``tests/regression.py``)."""
        return sorted((e.source, e.target, e.rule, e.edge_type, e.location)
                      for e in self.edges)

    def to_dict(self):
        def edge(e):
            return {"source": e.source, "target": e.target, "rule": e.rule,
                    "type": e.edge_type, "location": e.location}
        return {
            "format": self.fmt,
            "config": self.config.to_dict(),
            "statements_found": len(self.all_nodes),
            "proofs": len(self.proofs),
            "nodes": [{"label": n.label, "env": n.env, "index": n.index,
                       "name": n.display_name} for n in self.nodes],
            "edges": [edge(e) for e in self.edges],
            "dropped_edges": [edge(e) for e in self.dropped],
            "cycle_edges": sorted(list(k) for k in self.cycles),
        }


def run_pipeline(text, fmt="auto", config=None):
    """Parse *text* and build its dependency graph.

    *fmt* is ``"latex"``, ``"markdown"`` or ``"auto"`` (detected from the
    text).  LaTeX text is expected to be already expanded (see
    ``load_input``); the index registry for H4 is built from every
    statement, as on the page.
    """
    config = config or PipelineConfig()
    used_fmt, nodes, nbi, ltn, proofs, envs = parse_document(
        text, fmt=None if fmt in (None, "auto") else fmt)
    inc_nodes, inc_nbi, inc_ltn = select_nodes(nodes, ltn, config.include)
    registry = None
    if used_fmt == "latex" and config.mode == "infer":
        registry = build_index_registry(nodes, proofs, text)
    edges = raw_edges(inc_nodes, inc_nbi, inc_ltn, proofs, config, envs,
                      index_registry=registry)
    edges, dropped = finish_edges(edges, inc_nodes, config)
    return PipelineResult(fmt=used_fmt, nodes=inc_nodes, all_nodes=nodes,
                          proofs=proofs, envs=set(envs), edges=edges,
                          dropped=dropped, cycles=find_cycles(edges),
                          config=config, text=text)


def load_input(path, fmt="auto"):
    """Read what *path* names and return ``(text, fmt, is_collection)``.

    * a LaTeX main file: expanded with its ``\\input``/``\\include`` files
    * a Markdown file: read as is
    * a folder: its Markdown files joined as one glossary, in file-name
      order (``is_collection`` is True: no reading order, so callers
      default to ``ordered=False``)
    * ``-``: standard input

    *fmt* ``"auto"`` takes the format from the extension when there is
    one, else leaves it to ``parse_document`` to detect.
    """
    if path == "-":
        return sys.stdin.read(), fmt, False
    if os.path.isdir(path):
        files = markdown_files(path)
        if not files:
            raise FileNotFoundError(f"no Markdown files in {path}")
        return read_markdown_files(files), "markdown", True
    suffix = os.path.splitext(path)[1].lower()
    if fmt == "auto":
        fmt = FORMAT_BY_SUFFIX.get(suffix, "auto")
    if fmt == "latex" and suffix in (".tex", ".ltx"):
        from knowtex.core.file_expand import load_and_expand
        return load_and_expand(path), "latex", False
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read(), fmt, False
