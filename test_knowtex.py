#!/usr/bin/env python3
"""
Test suite for the knowtex package.

Run with:  pytest test_knowtex.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from knowtex.core.utils import (
    strip_comments,
    strip_subfile_wrapper,
    normalize_index_term,
    ensure_tex_ext,
)
from knowtex.core.parser import (
    is_theorem_like,
    parse_latex_structure,
)
from knowtex.core.structure import (
    detect_doc_class,
    find_chapter_ranges,
    find_section_ranges,
    assign_sections,
)
from knowtex.core.cycles import find_cycles
from knowtex.core.data import NodeInfo, ProofInfo, DependencyEdge
from knowtex.core.text_parser import parse_text_structure
from knowtex.deps.infer import run_inference, resolve_cycles
from knowtex.deps.index_registry import build_index_registry
from knowtex.deps.term_extraction import (
    _strip_latex_to_words,
    _extract_emph_terms,
    extract_defined_terms,
    _stem,
    _stem_words,
)
from knowtex.deps.manual import extract_manual_edges


def make_node(env, label, index, snippet="", pos=0, pos_end=0, display_name=None):
    if display_name is None:
        display_name = label.split(":")[-1] if ":" in label else label
    return NodeInfo(
        env=env, label=label, index=index,
        snippet=snippet, pos=pos, pos_end=pos_end,
        display_name=display_name,
    )


def make_proof(index, snippet, target_node_idx=None, target_label=None):
    return ProofInfo(
        index=index,
        target_label=target_label,
        snippet=snippet,
        pos=0,
        pos_end=len(snippet),
        target_node_idx=target_node_idx,
    )


def edges_as_set(edges):
    """Convert a list of DependencyEdge to a set of (source, target, rule) for easy assertion."""
    return {(e.source, e.target, e.rule) for e in edges}


def edge_pairs(edges):
    """Convert edges to set of (source, target) pairs."""
    return {(e.source, e.target) for e in edges}


# ############################################################
#  UTILS TESTS
# ############################################################

class TestStripComments:
    def test_simple_comment(self):
        assert strip_comments("hello % world") == "hello "

    def test_no_comment(self):
        assert strip_comments("hello world") == "hello world"

    def test_escaped_percent(self):
        result = strip_comments(r"50\% done")
        assert "50" in result
        assert "done" in result

    def test_multiline(self):
        text = "line1 % comment\nline2 % comment2"
        result = strip_comments(text)
        assert "line1" in result
        assert "line2" in result
        assert "comment" not in result


class TestStripSubfileWrapper:
    def test_full_subfile(self):
        text = r"""\documentclass[main.tex]{subfiles}
\begin{document}
Hello world.
\end{document}"""
        result = strip_subfile_wrapper(text)
        assert "Hello world." in result
        assert "documentclass" not in result
        assert "\\end{document}" not in result

    def test_no_document_env(self):
        text = "Just some text."
        assert strip_subfile_wrapper(text) == text


class TestNormalizeIndexTerm:
    def test_simple(self):
        assert normalize_index_term("functor") == "functor"

    def test_with_modifier(self):
        assert normalize_index_term("functor|textbf") == "functor"

    def test_hierarchy(self):
        assert normalize_index_term("algebra!group") == "algebra!group"

    def test_sort_key(self):
        assert normalize_index_term("iso@isomorphism") == "iso"

    def test_combined(self):
        assert normalize_index_term("cat!func@functor|see{functors}") == "cat!func"

    def test_empty(self):
        assert normalize_index_term("") == ""


class TestEnsureTexExt:
    def test_no_ext(self):
        assert ensure_tex_ext("file") == "file.tex"

    def test_has_ext(self):
        assert ensure_tex_ext("file.tex") == "file.tex"

    def test_other_ext(self):
        assert ensure_tex_ext("file.sty") == "file.sty"


class TestIsTheoremLike:
    def test_theorem(self):
        assert is_theorem_like("theorem") is True

    def test_proof(self):
        assert is_theorem_like("proof") is False

    def test_equation(self):
        assert is_theorem_like("equation") is False

    def test_custom(self):
        assert is_theorem_like("mytheorem") is True

    def test_empty(self):
        assert is_theorem_like("") is False

    def test_proof_alias(self):
        assert is_theorem_like("pf") is False
        assert is_theorem_like("Proof") is False


class TestParseLatexStructure:
    def test_basic(self):
        tex = r"""
\begin{theorem}\label{thm:main}
Main theorem.
\end{theorem}
\begin{proof}
Use Lemma.
\end{proof}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert len(nodes) == 1
        assert nodes[0].label == "thm:main"
        assert len(proofs) == 1
        assert "theorem" in envs

    def test_no_label_auto_generates(self):
        tex = r"\begin{lemma}No label here.\end{lemma}"
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert len(nodes) == 1
        assert nodes[0].label.startswith("lemma:")

    def test_proof_target_ref(self):
        tex = r"""
\begin{theorem}\label{thm:A}A\end{theorem}
\begin{theorem}\label{thm:B}B\end{theorem}
\begin{proof}[Proof of Theorem \ref{thm:A}]
Content.
\end{proof}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert len(proofs) == 1
        assert proofs[0].target_label == "thm:A"
        assert proofs[0].target_node_idx == 0

    def test_proof_target_proves(self):
        tex = r"""
\begin{theorem}\label{thm:X}X\end{theorem}
\begin{theorem}\label{thm:Y}Y\end{theorem}
\begin{proof}\proves{thm:X}
Content.
\end{proof}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert proofs[0].target_label == "thm:X"

    def test_display_name_from_label(self):
        tex = r"\begin{theorem}\label{thm:main}content\end{theorem}"
        nodes, *_ = parse_latex_structure(tex)
        assert nodes[0].display_name == "main"


class TestDetectDocClass:
    def test_book(self):
        assert detect_doc_class(r"\documentclass{book}") == "book"

    def test_article(self):
        assert detect_doc_class(r"\documentclass{article}") == "article"

    def test_report(self):
        assert detect_doc_class(r"\documentclass[12pt]{report}") == "book"

    def test_no_class(self):
        assert detect_doc_class("Hello world") == "article"


class TestFindRanges:
    def test_chapters(self):
        tex = r"""
\chapter{Introduction}
Intro text.
\chapter{Methods}
Methods text.
"""
        chapters = find_chapter_ranges(tex)
        assert len(chapters) == 2
        assert chapters[0]["title"] == "Introduction"
        assert chapters[1]["title"] == "Methods"

    def test_sections(self):
        tex = r"""
\section{Background}
\section{Results}
"""
        sections = find_section_ranges(tex)
        assert len(sections) == 2

    def test_no_chapters(self):
        assert find_chapter_ranges("No chapters here.") == []


class TestAssignSections:
    def test_basic(self):
        nodes = [
            make_node("theorem", "thm:1", 0, pos=50, pos_end=100),
            make_node("lemma", "lem:1", 1, pos=200, pos_end=250),
        ]
        ranges = [
            {"title": "Chapter 1", "start": 0, "end": 150},
            {"title": "Chapter 2", "start": 150, "end": 300},
        ]
        result = assign_sections(nodes, ranges)
        assert result["thm:1"] == "Chapter 1"
        assert result["lem:1"] == "Chapter 2"

    def test_ungrouped(self):
        nodes = [make_node("theorem", "thm:x", 0, pos=500)]
        ranges = [{"title": "Ch1", "start": 0, "end": 100}]
        result = assign_sections(nodes, ranges)
        assert result["thm:x"] == "(ungrouped)"


# ############################################################
#  INFERENCE TESTS
# ############################################################

class TestD1ProofRef:
    def test_basic_ref_in_proof(self):
        nodes = [
            make_node("theorem", "thm:A", 0),
            make_node("theorem", "thm:B", 1),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        proofs = [make_proof(2, r"\begin{proof}\ref{thm:A}\end{proof}", target_node_idx=1)]
        edges = run_inference(nodes, nbi, ltn, proofs)
        pairs = edge_pairs(edges)
        assert ("thm:A", "thm:B") in pairs

    def test_self_ref_ignored(self):
        nodes = [make_node("theorem", "thm:A", 0)]
        nbi = {0: nodes[0]}
        ltn = {"thm:A": nodes[0]}
        proofs = [make_proof(1, r"\begin{proof}\ref{thm:A}\end{proof}", target_node_idx=0)]
        edges = run_inference(nodes, nbi, ltn, proofs)
        assert len(edges) == 0

    def test_cref_in_proof(self):
        nodes = [
            make_node("theorem", "thm:A", 0),
            make_node("theorem", "thm:B", 1),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        proofs = [make_proof(2, r"\begin{proof}\Cref{thm:A}\end{proof}", target_node_idx=1)]
        edges = run_inference(nodes, nbi, ltn, proofs)
        assert ("thm:A", "thm:B") in edge_pairs(edges)


class TestD2StatementRef:
    def test_ref_in_statement(self):
        nodes = [
            make_node("theorem", "thm:A", 0),
            make_node("theorem", "thm:B", 1, snippet=r"\begin{theorem}By \ref{thm:A}\end{theorem}"),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = run_inference(nodes, nbi, ltn, [])
        assert ("thm:A", "thm:B", "D2") in edges_as_set(edges)


class TestH2Corollary:
    def test_corollary_no_ref(self):
        nodes = [
            make_node("theorem", "thm:A", 0),
            make_node("corollary", "cor:A", 1),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = run_inference(nodes, nbi, ltn, [])
        assert ("thm:A", "cor:A", "H2") in edges_as_set(edges)

    def test_corollary_with_ref_skipped(self):
        nodes = [
            make_node("theorem", "thm:A", 0),
            make_node("corollary", "cor:A", 1,
                      snippet=r"\begin{corollary}By \ref{thm:A}\end{corollary}"),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = run_inference(nodes, nbi, ltn, [])
        h2_edges = [e for e in edges if e.rule == "H2"]
        assert len(h2_edges) == 0


class TestH3Lemma:
    def test_lemma_to_theorem(self):
        nodes = [
            make_node("lemma", "lem:A", 0),
            make_node("theorem", "thm:B", 1),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = run_inference(nodes, nbi, ltn, [])
        assert ("lem:A", "thm:B", "H3") in edges_as_set(edges)

    def test_lemma_chain(self):
        nodes = [
            make_node("lemma", "lem:A", 0),
            make_node("lemma", "lem:B", 1),
            make_node("theorem", "thm:C", 2),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = run_inference(nodes, nbi, ltn, [])
        assert ("lem:A", "thm:C") in edge_pairs(edges)
        assert ("lem:B", "thm:C") in edge_pairs(edges)


# ############################################################
#  TERM EXTRACTION TESTS
# ############################################################

class TestStripLatexToWords:
    def test_basic(self):
        words = _strip_latex_to_words("hello world")
        assert "hello" in words
        assert "world" in words

    def test_math_removed(self):
        words = _strip_latex_to_words(r"The group $G$ acts on $X$")
        assert "the" in words
        assert "group" in words
        assert "acts" in words

    def test_short_words_skipped(self):
        words = _strip_latex_to_words("a b cd")
        assert "a" not in words
        assert "b" not in words
        assert "cd" in words


class TestExtractEmphTerms:
    def test_basic(self):
        terms = _extract_emph_terms(r"\emph{functor}")
        assert "functor" in terms

    def test_multiple(self):
        terms = _extract_emph_terms(r"\emph{group} and \textbf{ring}")
        assert "group" in terms
        assert "ring" in terms

    def test_latex_command_skipped(self):
        terms = _extract_emph_terms(r"\emph{\mathbb{R}}")
        assert len(terms) == 0


class TestExtractDefinedTerms:
    def test_basic(self):
        node = make_node("definition", "def:grp", 0,
                         snippet=r"\begin{definition}A \emph{group} is...\end{definition}")
        terms = extract_defined_terms(node)
        assert len(terms) >= 1
        raw_terms = [t[0].lower() for t in terms]
        assert "group" in raw_terms


class TestStemming:
    def test_stem(self):
        s = _stem("running")
        assert isinstance(s, str)
        assert len(s) > 0

    def test_stem_words(self):
        result = _stem_words(["running", "cats"])
        assert len(result) == 2


# ############################################################
#  CYCLE DETECTION TESTS
# ############################################################

class TestFindCycles:
    def test_no_cycle(self):
        edges = [
            DependencyEdge("A", "B", "deterministic", "proof", "D1"),
            DependencyEdge("B", "C", "deterministic", "proof", "D1"),
        ]
        assert find_cycles(edges) == set()

    def test_simple_cycle(self):
        edges = [
            DependencyEdge("A", "B", "deterministic", "proof", "D1"),
            DependencyEdge("B", "A", "deterministic", "proof", "D1"),
        ]
        result = find_cycles(edges)
        assert ("A", "B") in result
        assert ("B", "A") in result

    def test_triangle_cycle(self):
        edges = [
            DependencyEdge("A", "B", "deterministic", "proof", "D1"),
            DependencyEdge("B", "C", "deterministic", "proof", "D1"),
            DependencyEdge("C", "A", "deterministic", "proof", "D1"),
        ]
        result = find_cycles(edges)
        assert len(result) == 3

    def test_mixed_cycle_and_dag(self):
        edges = [
            DependencyEdge("A", "B", "deterministic", "proof", "D1"),
            DependencyEdge("B", "A", "deterministic", "proof", "D1"),
            DependencyEdge("C", "D", "deterministic", "proof", "D1"),
        ]
        result = find_cycles(edges)
        assert ("A", "B") in result
        assert ("B", "A") in result
        assert ("C", "D") not in result


class TestResolveCycles:
    """Cycle resolution: D4 edges that close a cycle are dropped, weakest
    first; explicit edges are never touched."""

    @staticmethod
    def d4(s, t):
        return DependencyEdge(s, t, "deterministic", "statement", "D4")

    @staticmethod
    def d2(s, t):
        return DependencyEdge(s, t, "deterministic", "statement", "D2")

    def test_acyclic_graph_is_unchanged(self):
        edges = [self.d2("A", "B"), self.d4("B", "C"), self.d4("A", "C")]
        kept, dropped = resolve_cycles(edges)
        assert kept == edges and dropped == []

    def test_term_match_against_explicit_reference_loses(self):
        # The author linked A from B (A -> B); D4 found the reverse.
        edges = [self.d2("A", "B"), self.d4("B", "A")]
        kept, dropped = resolve_cycles(edges)
        assert [e.key() for e in kept] == [("A", "B")]
        assert [e.key() for e in dropped] == [("B", "A")]

    def test_term_match_closing_an_explicit_path_loses(self):
        # A -> B -> C by references, C -> A by a term match.
        edges = [self.d2("A", "B"), self.d2("B", "C"), self.d4("C", "A")]
        kept, dropped = resolve_cycles(edges)
        assert [e.key() for e in dropped] == [("C", "A")]
        assert find_cycles(kept) == set()

    def test_explicit_cycles_are_kept(self):
        edges = [self.d2("A", "B"), self.d2("B", "A"), self.d4("A", "C")]
        kept, dropped = resolve_cycles(edges)
        assert kept == edges and dropped == []
        assert find_cycles(kept) == {("A", "B"), ("B", "A")}

    def test_hub_source_loses_in_a_d4_only_cycle(self):
        # D matched in two statements, C in one: D -> C is the weaker edge.
        edges = [self.d4("C", "D"), self.d4("D", "C"), self.d4("D", "E")]
        kept, dropped = resolve_cycles(edges)
        assert [e.key() for e in dropped] == [("D", "C")]
        assert find_cycles(kept) == set()

    def test_stem_only_match_loses_to_surface_match(self):
        # "functional" reaches "linear transformation" only through the stem
        # "function"; "linear transformation" occurs verbatim in "functional".
        text = """# Linear transformation
A function T between vector spaces is a **linear transformation** if ...

# Functional
A **functional** is a linear transformation into the ground field.
"""
        nodes, nbi, ltn, proofs, envs = parse_text_structure(text)
        edges = run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"},
                              ordered=False)
        keys = {e.key() for e in edges}
        assert ("definition:functional", "definition:linear-transformation") in keys
        assert ("definition:linear-transformation", "definition:functional") in keys
        kept, dropped = resolve_cycles(edges, nodes)
        assert [e.key() for e in dropped] == [
            ("definition:functional", "definition:linear-transformation")]
        assert find_cycles(kept) == set()

    def test_heuristic_edges_do_not_count_as_explicit(self):
        # An H4 guess pointing back must not cost the D4 edge.
        edges = [self.d4("A", "B"),
                 DependencyEdge("B", "A", "heuristic", "inferred", "H4")]
        kept, dropped = resolve_cycles(edges)
        assert kept == edges and dropped == []
        # ... but a reference does.
        edges = [self.d4("A", "B"), self.d2("B", "A")]
        assert [e.key() for e in resolve_cycles(edges)[1]] == [("A", "B")]

    def test_other_rules_are_not_breakable_by_default(self):
        edges = [self.d2("A", "B"),
                 DependencyEdge("B", "A", "heuristic", "inferred", "H2")]
        kept, dropped = resolve_cycles(edges)
        assert dropped == []
        kept, dropped = resolve_cycles(edges, breakable=("H2",))
        assert [e.key() for e in dropped] == [("B", "A")]


# ############################################################
#  MANUAL EDGE EXTRACTION TESTS
# ############################################################

class TestManualEdges:
    def test_uses_in_statement(self):
        nodes = [
            make_node("definition", "def:A", 0,
                      snippet=r"\begin{definition}\label{def:A}A\end{definition}"),
            make_node("theorem", "thm:B", 1,
                      snippet=r"\begin{theorem}\label{thm:B}\uses{def:A}B\end{theorem}"),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = extract_manual_edges(nodes, nbi, ltn, [])
        assert len(edges) == 1
        assert edges[0].source == "def:A"
        assert edges[0].target == "thm:B"
        assert edges[0].location == "statement"
        assert edges[0].rule == "manual"

    def test_uses_in_proof(self):
        nodes = [
            make_node("definition", "def:A", 0,
                      snippet=r"\begin{definition}\label{def:A}A\end{definition}"),
            make_node("theorem", "thm:B", 1,
                      snippet=r"\begin{theorem}\label{thm:B}B\end{theorem}"),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        proofs = [make_proof(
            2,
            r"\begin{proof}\uses{def:A}Proof.\end{proof}",
            target_node_idx=1,
        )]
        edges = extract_manual_edges(nodes, nbi, ltn, proofs)
        assert len(edges) == 1
        assert edges[0].source == "def:A"
        assert edges[0].target == "thm:B"
        assert edges[0].location == "proof"

    def test_multiple_uses(self):
        nodes = [
            make_node("definition", "def:A", 0,
                      snippet=r"\begin{definition}\label{def:A}A\end{definition}"),
            make_node("definition", "def:B", 1,
                      snippet=r"\begin{definition}\label{def:B}B\end{definition}"),
            make_node("theorem", "thm:C", 2,
                      snippet=r"\begin{theorem}\label{thm:C}\uses{def:A, def:B}C\end{theorem}"),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = extract_manual_edges(nodes, nbi, ltn, [])
        pairs = edge_pairs(edges)
        assert ("def:A", "thm:C") in pairs
        assert ("def:B", "thm:C") in pairs

    def test_self_uses_ignored(self):
        nodes = [
            make_node("theorem", "thm:A", 0,
                      snippet=r"\begin{theorem}\label{thm:A}\uses{thm:A}A\end{theorem}"),
        ]
        nbi = {n.index: n for n in nodes}
        ltn = {n.label: n for n in nodes}
        edges = extract_manual_edges(nodes, nbi, ltn, [])
        assert len(edges) == 0


# ############################################################
#  INDEX REGISTRY TESTS
# ############################################################

class TestBuildIndexRegistry:
    def test_basic(self):
        nodes = [
            make_node("definition", "def:1", 0,
                      snippet=r"\begin{definition}\index{group}\end{definition}"),
            make_node("theorem", "thm:1", 1,
                      snippet=r"\begin{theorem}\index{ring}\end{theorem}"),
        ]
        reg = build_index_registry(nodes, [], "")
        assert "group" in reg["term_to_first_node"]
        assert reg["term_to_first_node"]["group"] == "def:1"

    def test_hierarchy(self):
        nodes = [
            make_node("definition", "def:1", 0,
                      snippet=r"\begin{definition}\index{algebra!group}\end{definition}"),
        ]
        reg = build_index_registry(nodes, [], "")
        assert len(reg["hierarchy_links"]) >= 1


# ############################################################
#  INTEGRATION TESTS
# ############################################################

class TestFullPipeline:
    """Test the complete flow: parse -> infer -> cycle check."""

    def test_simple_document(self):
        tex = r"""
\begin{definition}\label{def:group}
A \emph{group} is a set with a binary operation.
\end{definition}

\begin{theorem}\label{thm:lagrange}
Lagrange's theorem: the order of a subgroup divides
the order of the group.
\end{theorem}

\begin{proof}
By \ref{def:group}, consider the cosets...
\end{proof}

\begin{corollary}\label{cor:prime}
Every group of prime order is cyclic.
\end{corollary}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert len(nodes) == 3
        assert "definition" in envs
        assert "theorem" in envs
        assert "corollary" in envs

        edges = run_inference(nodes, nbi, ltn, proofs)
        pairs = edge_pairs(edges)

        # D1: proof references def:group -> thm:lagrange
        assert ("def:group", "thm:lagrange") in pairs

        # H2: corollary -> nearest theorem
        assert ("thm:lagrange", "cor:prime") in pairs

        # No cycles expected
        cycle_edges = find_cycles(edges)
        assert len(cycle_edges) == 0



class TestStripLatexDisplayMath:
    def test_words_after_display_math_are_kept(self):
        from knowtex.deps.term_extraction import _strip_latex_to_words
        s = r"Let $$\vert f \vert^p$$ be finite. The map $A$ is called the \emph{total derivative} of $f$."
        words = _strip_latex_to_words(s)
        assert "total" in words and "derivative" in words and "finite" in words
        assert "vert" not in words


# ----------------------------------------------------------------------
# Regression tests for the LaTeX parser / registry / expansion fixes
# ----------------------------------------------------------------------

class TestNestedEnvironments:
    def test_inner_math_environments_are_not_nodes(self):
        tex = r"""
\begin{theorem}\label{t}
\begin{aligned} a &= b \end{aligned}
\begin{alignat*}{2} c &= d \end{alignat*}
\end{theorem}
\begin{figure*} x \end{figure*}
\begin{proof*} trivial \end{proof*}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert [n.label for n in nodes] == ["t"]
        assert len(proofs) == 1 and proofs[0].target_node_idx == 0

    def test_statement_nested_in_statement_does_not_steal_the_proof(self):
        tex = r"""
\begin{theorem}\label{outer}
Text. \begin{claim}\label{inner} c \end{claim}
\end{theorem}
\begin{proof} p \end{proof}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert {n.label for n in nodes} == {"outer", "inner"}
        assert proofs[0].target_node_idx == ltn["outer"].index

    def test_duplicate_explicit_labels_are_disambiguated(self):
        tex = r"""
\begin{theorem}\label{a} one \end{theorem}
\begin{theorem}\label{a} two \end{theorem}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert len(nodes) == 2 and len(ltn) == 2
        assert ltn["a"].index == 0 and "a:1" in ltn

    def test_proof_of_ref_with_pfof_alias(self):
        tex = r"""
\begin{theorem}\label{t1} a \end{theorem}
\begin{theorem}\label{t2} b \end{theorem}
\begin{pfof}[Proof of Theorem \ref{t1}] c \end{pfof}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert proofs[0].target_label == "t1"
        assert proofs[0].target_node_idx == 0


class TestIndexRegistryOrder:
    def test_emph_before_index_wins(self):
        n0 = make_node("theorem", "t0", 0, snippet=r"\begin{theorem} A \emph{widget} is nice. \end{theorem}")
        n1 = make_node("remark", "r1", 1, snippet=r"\begin{remark} Widgets again. \end{remark}")
        n2 = make_node("example", "e2", 2, snippet=r"\begin{example} \index{widget} \end{example}")
        reg = build_index_registry([n0, n1, n2], [], "")
        assert reg["term_to_first_node"]["widget"] == "t0"

    def test_see_entries_are_not_uses(self):
        n0 = make_node("theorem", "t0", 0, snippet=r"\begin{theorem} \index{gadget|see{widget}} \end{theorem}")
        n1 = make_node("theorem", "t1", 1, snippet=r"\begin{theorem} \index{widget} \end{theorem}")
        reg = build_index_registry([n0, n1], [], n0.snippet + n1.snippet)
        assert reg["term_to_first_node"]["widget"] == "t1"


class TestH4AndD4OnLatex:
    TEX = r"""
\begin{definition}\label{def:group}
A \emph{group} is a set with an associative operation.
\end{definition}
\begin{theorem}\label{thm:widget}
Every \index{widget} widget is fine.
\end{theorem}
\begin{remark}\label{rem:use}
Groups and widgets appear together here.
\end{remark}
"""

    def test_d4_and_h4_edges(self):
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(self.TEX)
        reg = build_index_registry(nodes, proofs, self.TEX)
        edges = run_inference(nodes, nbi, ltn, proofs, index_registry=reg,
                              definition_envs={"definition"})
        triples = {(e.rule, e.source, e.target) for e in edges}
        assert ("D4", "def:group", "rem:use") in triples
        assert ("H4", "thm:widget", "rem:use") in triples


class TestFileExpansion:
    def test_input_paths_resolve_relative_to_main_document(self, tmp_path):
        from knowtex.core.file_expand import load_and_expand
        (tmp_path / "chapters").mkdir()
        (tmp_path / "main.tex").write_text(r"\input{chapters/ch1}", encoding="utf-8")
        (tmp_path / "chapters" / "ch1.tex").write_text(
            "CH1\n" + r"\input{chapters/sec1}", encoding="utf-8")
        (tmp_path / "chapters" / "sec1.tex").write_text("SEC1", encoding="utf-8")
        out = load_and_expand(str(tmp_path / "main.tex"))
        assert "CH1" in out and "SEC1" in out and "missing file" not in out

    def test_paths_outside_the_project_are_blocked(self, tmp_path):
        from knowtex.core.file_expand import load_and_expand
        from knowtex.core.utils import is_within_project
        proj = tmp_path / "proj"; proj.mkdir()
        (tmp_path / "secret.tex").write_text("SECRET", encoding="utf-8")
        (proj / "main.tex").write_text(r"\input{../secret}", encoding="utf-8")
        out = load_and_expand(str(proj / "main.tex"))
        assert "SECRET" not in out and "blocked path" in out
        assert is_within_project(str(proj / "a.tex"), str(proj))
        assert not is_within_project(str(tmp_path / "secret.tex"), str(proj))

    def test_subfile_wrapper_is_stripped(self, tmp_path):
        from knowtex.core.file_expand import load_and_expand
        (tmp_path / "main.tex").write_text(r"\subfile{part}", encoding="utf-8")
        (tmp_path / "part.tex").write_text(
            "\\documentclass[main]{subfiles}\n\\begin{document}\nBODY\n\\end{document}\n",
            encoding="utf-8")
        out = load_and_expand(str(tmp_path / "main.tex"))
        assert "BODY" in out and "documentclass" not in out


class TestIncludeOnly:
    def test_paths_and_nested_braces(self, tmp_path):
        from knowtex.core.file_expand import load_and_expand
        (tmp_path / "gr").mkdir(); (tmp_path / "cover").mkdir()
        (tmp_path / "main.tex").write_text(
            "\\includeonly{\n"
            "cover/a,%\n"
            "\\ifbool{hc}{cover/b}{cover/a,cover/c},\n"
            "gr/gr1,gr/gr2.tex%\n"
            "}\n"
            "\\include{cover/a}\\include{cover/b}\\include{cover/c}\n"
            "\\include{gr/gr1}\\include{gr/gr2}\\include{gr/gr3}\n", encoding="utf-8")
        for n in ("cover/a", "cover/b", "cover/c", "gr/gr1", "gr/gr2", "gr/gr3"):
            (tmp_path / (n + ".tex")).write_text("FILE-" + n.replace("/", "-") + "\n", encoding="utf-8")
        out = load_and_expand(str(tmp_path / "main.tex"))
        for present in ("FILE-cover-a", "FILE-cover-b", "FILE-cover-c", "FILE-gr-gr1", "FILE-gr-gr2"):
            assert present in out, present
        assert "FILE-gr-gr3" not in out and "skipped by \\includeonly: gr/gr3" in out
