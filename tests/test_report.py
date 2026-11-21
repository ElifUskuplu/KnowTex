#!/usr/bin/env python3
"""Tests of the ``disabled_rules`` ablation switch and the evaluation
helpers (``knowtex/evaluation.py``).

Run with:  pytest tests/test_report.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))   # repository root

from knowtex.evaluation import (  # noqa: E402
    Gold, blueprint_edges_from_text, compare, reachability,
)
from knowtex.pipeline import PipelineConfig, run_pipeline  # noqa: E402

# A lemma right before a theorem whose proof cites it: D1 and H3 propose
# the same edge.  A corollary whose proof cites the theorem: D1 gives it
# an incoming edge, so H2 skips it.  A second corollary with a \ref in its
# statement: H2 skips it for that reason.
DOC = r"""
\documentclass{article}
\begin{document}
\begin{definition}\label{d1}
A \emph{widget} is a gadget.
\end{definition}
\begin{lemma}\label{l1}
Widgets exist.
\end{lemma}
\begin{theorem}\label{t1}
Every widget is a gadget.
\end{theorem}
\begin{proof}
By Lemma~\ref{l1}.
\end{proof}
\begin{corollary}\label{c1}
Gadgets exist.
\end{corollary}
\begin{proof}
By Theorem~\ref{t1}.
\end{proof}
\begin{corollary}\label{c2}
See Theorem~\ref{t1}.
\end{corollary}
\begin{corollary}\label{c3}
Nothing cited here.
\end{corollary}
\end{document}
"""


def pairs(result):
    return sorted((e.source, e.target, e.rule) for e in result.edges)


class TestDisabledRules:
    def test_disabling_d1_hands_the_edge_to_h3(self):
        res = run_pipeline(DOC, "latex", PipelineConfig(tred=False, disabled_rules={"D1"}))
        rules = {(s, t): r for s, t, r in pairs(res)}
        assert rules[("l1", "t1")] == "H3"
        assert all(r != "D1" for r in rules.values())
        # c1 now has no incoming author edge, so H2 links it to the theorem
        assert rules[("t1", "c1")] == "H2"

    def test_disabling_everything_leaves_nothing(self):
        res = run_pipeline(DOC, "latex", PipelineConfig(
            disabled_rules={"D1", "D2", "D4", "H2", "H3", "H4"}))
        assert res.edges == []

    def test_config_roundtrip_and_cli_flag(self, tmp_path):
        import json
        from knowtex.cli import main
        c = PipelineConfig.from_dict({"disabled_rules": ["H3", "D4"]})
        assert c.disabled_rules == frozenset({"D4", "H3"})
        assert PipelineConfig.from_dict(c.to_dict()) == c
        src = tmp_path / "d.tex"
        src.write_text(DOC)
        out = tmp_path / "o.json"
        assert main([str(src), "--quiet", "--disable-rule", "D4", "--json", str(out)]) == 0
        j = json.loads(out.read_text())
        assert j["config"]["disabled_rules"] == ["D4"]
        assert all(e["rule"] != "D4" for e in j["edges"])


class TestEvaluation:
    def test_compare_metrics(self):
        gold = {("a", "b"), ("b", "c"), ("c", "d")}
        pred = {("a", "b"), ("a", "c"), ("x", "y")}
        m = compare(pred, gold)
        assert (m["tp"], m["fp"], m["fn"]) == (1, 2, 2)
        assert m["precision"] == pytest.approx(1 / 3)
        assert m["recall"] == pytest.approx(1 / 3)
        assert m["path_justified"] == 1                 # a->c follows a->b->c in gold
        assert m["truly_spurious"] == 1                 # x->y
        assert m["path_precision"] == pytest.approx(2 / 3)
        assert m["path_recovered"] == 0                 # b->c, c->d: no predicted path
        assert m["extra_edges"] == [("a", "c"), ("x", "y")]

    def test_path_recall(self):
        gold = {("a", "c")}
        pred = {("a", "b"), ("b", "c")}
        m = compare(pred, gold)
        assert m["tp"] == 0 and m["path_recovered"] == 1 and m["path_recall"] == 1.0

    def test_reachability_is_transitive_not_reflexive(self):
        reach = reachability({("a", "b"), ("b", "c")})
        assert reach("a", "c") and not reach("c", "a") and not reach("a", "a")

    def test_style_accuracy(self):
        gold = {("a", "b"), ("b", "c")}
        m = compare(gold, gold, {("a", "b"): "solid", ("b", "c"): "dashed"},
                    {("a", "b"): "solid", ("b", "c"): "solid"})
        assert (m["style_matches"], m["style_total"]) == (1, 2)

    def test_blueprint_edges_from_svg(self):
        svg = ('<g id="e1" class="edge"><title>a-&gt;b</title><path stroke="black"/></g>'
               '<g id="e2" class="edge"><title>b-&gt;c</title>'
               '<path stroke="black" stroke-dasharray="5,2"/></g>'
               '<g id="n1" class="node"><title>a</title></g>')
        assert blueprint_edges_from_text(svg) == [("a", "b", "solid"), ("b", "c", "dashed")]

    def test_gold_maps_predicted_labels(self):
        res = run_pipeline(DOC, "latex")
        gold = Gold("x", "test", {("L1", "T1")}, map_pred=str.upper)
        assert ("L1", "T1") in gold.pred_pairs(res)


@pytest.fixture(scope="module")
def evals():
    """Every paper dataset evaluated against its gold standard."""
    from knowtex.evaluation import evaluate, load_gold, run_dataset
    from datasets import load_configs
    out = {}
    for cfg in load_configs():
        gold = load_gold(cfg)
        res = run_dataset(cfg, "infer")
        if gold is not None and res is not None:
            out[cfg["name"]] = evaluate(res, gold)
    return out


class TestPaperNumbers:
    """The evaluation module reproduces the figures reported in the paper
    (datasets whose input is missing are skipped)."""

    @pytest.mark.parametrize("name,p,r,f1", [
        ("group_theory", 0.853, 0.906, 0.879),
        ("bct", 0.708, 0.754, 0.730),
        ("pfr", 0.901, 0.769, 0.830),
        ("chicago", 0.739, 1.000, 0.850),
    ])
    def test_precision_recall_f1(self, evals, name, p, r, f1):
        if name not in evals:
            pytest.skip("input missing")
        m = evals[name]
        assert (round(m["precision"], 3), round(m["recall"], 3), round(m["f1"], 3)) == (p, r, f1)

    def test_path_based_figures(self, evals):
        if "group_theory" in evals:
            assert round(evals["group_theory"]["path_precision"], 3) == 0.971
            assert evals["group_theory"]["truly_spurious"] == 2
        if "pfr" in evals:
            assert round(evals["pfr"]["path_precision"], 3) == 0.922
            assert round(evals["pfr"]["path_recall"], 3) == 0.819
            assert round(evals["pfr"]["style_accuracy"], 3) == 0.965
        if "bct" in evals:
            assert (evals["bct"]["style_matches"], evals["bct"]["style_total"]) == (43, 46)
