#!/usr/bin/env python3
"""Tests of multi-target proof headers (D3 with several ``\\ref``s,
``\\proves{a,b}``).

Run with:  pytest tests/test_d3_multi_target.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))   # repository root

from knowtex.core.data import proof_targets  # noqa: E402
from knowtex.core.parser import parse_latex_structure  # noqa: E402
from knowtex.deps.infer import run_inference  # noqa: E402
from knowtex.deps.manual import extract_manual_edges  # noqa: E402
from knowtex.pipeline import PipelineConfig, run_pipeline  # noqa: E402

HEAD = r"""
\begin{lemma}\label{lem:tool} A tool. \end{lemma}
\begin{theorem}\label{thm:a} A. \end{theorem}
\begin{theorem}\label{thm:b} B. \end{theorem}
\begin{theorem}\label{thm:c} C. \end{theorem}
"""


def parse(doc):
    nodes, nbi, ltn, proofs, envs = parse_latex_structure(doc)
    return nodes, nbi, ltn, proofs


def d1_pairs(doc):
    nodes, nbi, ltn, proofs = parse(doc)
    return sorted((e.source, e.target) for e in run_inference(nodes, nbi, ltn, proofs)
                  if e.rule == "D1")


class TestD3MultiTarget:
    def test_two_target_header(self):
        doc = HEAD + r"\begin{proof}[Proof of Theorems \ref{thm:a} and \ref{thm:b}] By \ref{lem:tool}. \end{proof}"
        nodes, nbi, ltn, proofs = parse(doc)
        p = proofs[0]
        assert p.target_label == "thm:a" and p.extra_target_labels == ("thm:b",)
        assert [nbi[i].label for i in proof_targets(p)] == ["thm:a", "thm:b"]
        assert d1_pairs(doc) == [("lem:tool", "thm:a"), ("lem:tool", "thm:b")]

    def test_three_targets_with_and_and_commas(self):
        doc = HEAD + r"\begin{proof}[Proof of \cref{thm:a}, \Cref{thm:b} and \ref{thm:c}] Use \ref{lem:tool}. \end{proof}"
        assert d1_pairs(doc) == [("lem:tool", "thm:a"), ("lem:tool", "thm:b"), ("lem:tool", "thm:c")]

    def test_cref_comma_list_in_header(self):
        doc = HEAD + r"\begin{proof}[Proof of \cref{thm:a,thm:b}] Use \ref{lem:tool}. \end{proof}"
        assert d1_pairs(doc) == [("lem:tool", "thm:a"), ("lem:tool", "thm:b")]

    def test_single_target_header_unchanged(self):
        doc = HEAD + r"\begin{proof}[Proof of Theorem \ref{thm:a}] Use \ref{lem:tool}. \end{proof}"
        nodes, nbi, ltn, proofs = parse(doc)
        p = proofs[0]
        assert p.extra_target_labels == () and p.extra_target_idxs == ()
        assert proof_targets(p) == [ltn["thm:a"].index]
        assert d1_pairs(doc) == [("lem:tool", "thm:a")]

    def test_proves_comma_list(self):
        doc = HEAD + r"\begin{proof}\proves{thm:a, thm:c} Use \ref{lem:tool}. \end{proof}"
        assert d1_pairs(doc) == [("lem:tool", "thm:a"), ("lem:tool", "thm:c")]

    def test_unresolvable_label_is_ignored(self):
        doc = HEAD + r"\begin{proof}[Proof of \ref{thm:nope} and \ref{thm:b}] Use \ref{lem:tool}. \end{proof}"
        nodes, nbi, ltn, proofs = parse(doc)
        p = proofs[0]
        assert p.target_node_idx == ltn["thm:b"].index and p.extra_target_idxs == ()
        assert d1_pairs(doc) == [("lem:tool", "thm:b")]

    def test_all_labels_unresolvable_falls_back_to_h1(self):
        doc = HEAD + r"\begin{proof}[Proof of \ref{x} and \ref{y}] Use \ref{lem:tool}. \end{proof}"
        nodes, nbi, ltn, proofs = parse(doc)
        assert proofs[0].target_node_idx == ltn["thm:c"].index      # the statement just before
        assert d1_pairs(doc) == [("lem:tool", "thm:c")]

    def test_manual_uses_reaches_every_target(self):
        doc = HEAD + r"\begin{proof}[Proof of \ref{thm:a} and \ref{thm:b}]\uses{lem:tool} Done. \end{proof}"
        nodes, nbi, ltn, proofs = parse(doc)
        pairs = sorted((e.source, e.target) for e in extract_manual_edges(nodes, nbi, ltn, proofs))
        assert pairs == [("lem:tool", "thm:a"), ("lem:tool", "thm:b")]

    def test_a_target_is_never_its_own_source(self):
        doc = HEAD + r"\begin{proof}[Proof of \ref{thm:a} and \ref{thm:b}] See \ref{thm:a} and \ref{lem:tool}. \end{proof}"
        assert d1_pairs(doc) == [("lem:tool", "thm:a"), ("lem:tool", "thm:b"), ("thm:a", "thm:b")]
