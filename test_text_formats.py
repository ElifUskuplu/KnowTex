#!/usr/bin/env python3
"""Tests for the format-independent front-ends and the pure-Python graph
helpers (Markdown parser, format detection, DOT output,
transitive reduction).

Run with:  pytest test_text_formats.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from knowtex.core.formats import detect_format, parse_document
from knowtex.core.text_parser import parse_text_structure, strip_markup, slugify
from knowtex.core.parser import parse_latex_structure
from knowtex.core.dot import build_dot
from knowtex.core.cycles import transitive_reduction, find_cycles
from knowtex.core.data import DependencyEdge
from knowtex.deps.infer import run_inference, node_refs, proof_refs
from knowtex.deps.term_extraction import node_words, defined_term_strings


MD_DOC = """
# Chapter 1

## Definition 1.1 (Group)
A **group** is a set with an associative binary operation.

## Definition 1.2
A group is called **abelian** if the operation is commutative.

**Theorem 1.3 (Lagrange).** Let $G$ be a finite group and $H$ a subgroup.

*Proof.* Count cosets, see [Definition 1.1](#definition:1.1). ∎

Corollary 1.4. Every group of prime order is cyclic.
"""

TXT_DOC = """Definition 2.1. A subset H of a group G is called a subgroup if it is closed.

Theorem 2.2. Let H be a subgroup of a finite group G. Then |H| divides |G|.

Proof of Theorem 2.2. By Definition 2.1 the cosets partition G. QED

Theorem provers are software, not statements.
"""

GLOSSARY = """---
 layout: page
 title: group
 permalink: /chicago/group
---
A **group** is a set with an operation.

---
 title: abelian group
 permalink: /chicago/abelian_group
---
A [group](https://example.org/chicago/group) is **abelian** if it commutes.

---
 title: ring
 permalink: /chicago/ring
---
A **ring** is an [abelian](https://example.org/chicago/abelian) [group](https://example.org/chicago/group) with a product.
"""


class TestDetectFormat:
    def test_latex(self):
        assert detect_format(r"\begin{theorem} x \end{theorem}") == "latex"

    def test_markdown_heading(self):
        assert detect_format("## Definition 1\ntext") == "markdown"

    def test_markdown_bold(self):
        assert detect_format("A **group** is a set.") == "markdown"

    def test_plain(self):
        assert detect_format(TXT_DOC) == "markdown"

    def test_latex_inside_markdown_math_is_not_latex(self):
        md = "## Definition 1 (Matrix)\nA **matrix** is $$\\begin{bmatrix} a & b \\end{bmatrix}$$ of numbers.\n"
        assert detect_format(md) == "markdown"


class TestMarkdownParser:
    def test_blocks_and_kinds(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(MD_DOC)
        assert [n.env for n in nodes] == ["definition", "definition", "theorem", "corollary"]
        assert envs == {"definition", "theorem", "corollary"}
        assert len(proofs) == 1

    def test_labels_from_numbers(self):
        nodes, *_ = parse_text_structure(MD_DOC)
        assert [n.label for n in nodes] == [
            "definition:1.1", "definition:1.2", "theorem:1.3", "corollary:1.4"]

    def test_display_names(self):
        nodes, *_ = parse_text_structure(MD_DOC)
        assert nodes[0].display_name == "Group"
        assert nodes[2].display_name == "Lagrange"

    def test_defined_terms(self):
        nodes, *_ = parse_text_structure(MD_DOC)
        assert nodes[0].defined_terms == ("Group",)
        assert nodes[1].defined_terms == ("abelian",)
        assert nodes[2].defined_terms == ()

    def test_section_heading_is_not_a_node(self):
        nodes, *_ = parse_text_structure(MD_DOC)
        assert all("chapter" not in n.label for n in nodes)

    def test_proof_association_and_link_ref(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(MD_DOC)
        p = proofs[0]
        assert p.target_node_idx == nodes[2].index   # H1: nearest statement
        assert p.refs == ("definition:1.1",)

    def test_text_is_markup_free(self):
        nodes, *_ = parse_text_structure(MD_DOC)
        assert "**" not in nodes[0].text
        assert "$" not in nodes[2].text
        assert "group" in node_words(nodes[0])

    def test_inference_runs(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(MD_DOC)
        edges = run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"})
        keys = {(e.rule, e.source, e.target) for e in edges}
        assert ("D1", "definition:1.1", "theorem:1.3") in keys
        assert ("D4", "definition:1.1", "definition:1.2") in keys
        assert ("H2", "theorem:1.3", "corollary:1.4") in keys


class TestKeywordOnlyText:
    def test_blocks(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(TXT_DOC)
        assert [n.label for n in nodes] == ["definition:2.1", "theorem:2.2"]
        assert len(proofs) == 1

    def test_sentence_starting_with_keyword_is_ignored(self):
        nodes, *_ = parse_text_structure(TXT_DOC)
        assert len(nodes) == 2

    def test_called_a_term(self):
        nodes, *_ = parse_text_structure(TXT_DOC)
        assert nodes[0].defined_terms == ("subgroup",)

    def test_proof_of_theorem_target(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(TXT_DOC)
        assert proofs[0].target_label == "theorem:2.2"
        assert proofs[0].target_node_idx == 1

    def test_textual_numbered_ref(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(TXT_DOC)
        assert proofs[0].refs == ("definition:2.1",)
        edges = run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"})
        assert {(e.rule, e.source, e.target) for e in edges} == {
            ("D1", "definition:2.1", "theorem:2.2")}


class TestGlossary:
    def test_front_matter_entries(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(GLOSSARY)
        assert [n.label for n in nodes] == [
            "definition:group", "definition:abelian-group", "definition:ring"]
        assert nodes[1].display_name == "abelian group"

    def test_entry_terms_are_titles_only(self):
        nodes, *_ = parse_text_structure(GLOSSARY)
        assert nodes[1].defined_terms == ("abelian group",)

    def test_links_resolve_by_slug(self):
        nodes, *_ = parse_text_structure(GLOSSARY)
        assert nodes[1].refs == ("definition:group",)
        # broken link target "abelian" is dropped, "group" resolves
        assert nodes[2].refs == ("definition:group",)

    def test_d2_and_d4(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(GLOSSARY)
        edges = run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"})
        keys = {(e.rule, e.source, e.target) for e in edges}
        assert ("D2", "definition:group", "definition:abelian-group") in keys
        assert ("D4", "definition:abelian-group", "definition:ring") in keys

    def test_headings_as_entries_auto(self):
        doc = "## group\nA **group** is a set.\n\n## ring\nA ring is a [group](#group).\n"
        nodes, nbi, ltn, proofs, envs = parse_text_structure(doc)
        assert [n.label for n in nodes] == ["definition:group", "definition:ring"]
        assert nodes[1].refs == ("definition:group",)


class TestParseDocument:
    def test_dispatch_latex(self):
        fmt, nodes, *_ = parse_document(r"\begin{lemma}\label{l}x\end{lemma}")
        assert fmt == "latex" and nodes[0].label == "l"

    def test_dispatch_markdown(self):
        fmt, nodes, *_ = parse_document(MD_DOC)
        assert fmt == "markdown" and len(nodes) == 4

    def test_explicit_format(self):
        fmt, nodes, *_ = parse_document(TXT_DOC, fmt="markdown")
        assert fmt == "markdown" and len(nodes) == 2

    def test_unknown_format_is_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            parse_document(TXT_DOC, fmt="text")


class TestLatexAccessorsUnchanged:
    """LaTeX nodes leave the new fields None and still derive everything
    from the snippet."""

    def test_refs_from_snippet(self):
        tex = r"""
\begin{theorem}\label{thm:A}A\end{theorem}
\begin{theorem}\label{thm:B}Uses \ref{thm:A}.\end{theorem}
\begin{proof}By \Cref{thm:A}.\end{proof}
"""
        nodes, nbi, ltn, proofs, envs = parse_latex_structure(tex)
        assert nodes[1].refs is None and nodes[1].text is None
        assert node_refs(nodes[1]) == ["thm:A"]
        assert proof_refs(proofs[0]) == ["thm:A"]

    def test_terms_from_snippet(self):
        tex = r"\begin{definition}\label{d}A \emph{normal subgroup} is\index{coset} ...\end{definition}"
        nodes, *_ = parse_latex_structure(tex)
        assert defined_term_strings(nodes[0]) == ["normal subgroup", "coset"]


class TestDot:
    def test_dot_contains_nodes_edges_and_styles(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(MD_DOC)
        edges = run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"})
        cfg = {e: {"shape": "box", "border": "Blue", "fill": "White"} for e in envs}
        dot = build_dot(nodes, edges, cfg, cycle_edges=find_cycles(edges))
        assert dot.startswith("digraph knowtex {")
        assert '"definition:1.1" [label="Group"' in dot
        assert '"definition:1.1" -> "theorem:1.3" [style="solid"' in dot
        assert '"theorem:1.3" -> "corollary:1.4" [style="dotted"' in dot
        assert "__legend__" in dot

    def test_filter_envs_hides_nodes(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(MD_DOC)
        cfg = {e: {} for e in envs}
        dot = build_dot(nodes, [], cfg, filter_envs={"theorem"}, add_legend=False)
        assert '"theorem:1.3"' in dot and '"definition:1.1"' not in dot


class TestTransitiveReduction:
    def _e(self, s, t):
        return DependencyEdge(s, t, "deterministic", "statement", "D2")

    def test_removes_shortcut(self):
        edges = [self._e("a", "b"), self._e("b", "c"), self._e("a", "c")]
        kept = {(e.source, e.target) for e in transitive_reduction(edges)}
        assert kept == {("a", "b"), ("b", "c")}

    def test_keeps_cycle_edges(self):
        edges = [self._e("a", "b"), self._e("b", "a"), self._e("a", "c"), self._e("b", "c")]
        kept = {(e.source, e.target) for e in transitive_reduction(edges)}
        assert ("a", "b") in kept and ("b", "a") in kept


class TestHelpers:
    def test_slugify(self):
        assert slugify("Abelian Group") == "abelian-group"
        assert slugify("abelian_group") == "abelian-group"
        assert slugify("σ-algebra") == "σ-algebra"

    def test_strip_markup(self):
        assert strip_markup("A **ring** $R$ [link](http://x/y) `c`").split() == ["A", "ring", "link"]


# ----------------------------------------------------------------------
# Regression tests for the parser / reduction fixes
# ----------------------------------------------------------------------

class TestTransitiveReductionCycles:
    def test_edge_leaving_a_cycle_is_kept(self):
        # a<->b is a cycle; a->c must survive: the only "other path" b->a->c
        # would use the edge under test.
        edges = [DependencyEdge("a", "b", "x", "", "D2"),
                 DependencyEdge("b", "a", "x", "", "D2"),
                 DependencyEdge("a", "c", "x", "", "D2")]
        kept = {(e.source, e.target) for e in transitive_reduction(edges)}
        assert kept == {("a", "b"), ("b", "a"), ("a", "c")}

    def test_reduction_through_another_component_still_applies(self):
        edges = [DependencyEdge("a", "b", "x", "", "D2"),
                 DependencyEdge("b", "c", "x", "", "D2"),
                 DependencyEdge("a", "c", "x", "", "D2")]
        kept = {(e.source, e.target) for e in transitive_reduction(edges)}
        assert kept == {("a", "b"), ("b", "c")}


class TestMarkdownHeadingBlocks:
    DOC = """# Notes

## Definition 1 (Group)

A **group** is a set with an associative operation.

More about groups, over a second paragraph.

## Theorem 2 (Lagrange) {#lag}

Let $G$ be a finite group, see Definition 1.

## Proof of Theorem 2

Count the cosets of Definition 1. QED.

## Proof

This orphan proof belongs to Theorem 2 as well. ∎
"""

    def test_heading_block_survives_blank_lines(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(self.DOC)
        by = {n.label: n for n in nodes}
        assert "second paragraph" in by["definition:1"].text
        assert by["lag"].refs == ("definition:1",)

    def test_proof_heading_is_a_proof(self):
        nodes, nbi, ltn, proofs, envs = parse_text_structure(self.DOC)
        assert len(proofs) == 2
        assert proofs[0].target_label == "lag"          # resolved through the number
        assert proofs[0].target_node_idx == 1
        assert proofs[1].target_node_idx == 1           # H1: last statement
        edges = run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"})
        assert ("D1", "definition:1", "lag") in {(e.rule, e.source, e.target) for e in edges}

    def test_qed_with_trailing_period_closes_the_proof(self):
        text = "Theorem 1. Claim.\n\nProof. Easy. Q.E.D.\n\nUnrelated paragraph.\n"
        nodes, nbi, ltn, proofs, envs = parse_text_structure(text)
        assert "Unrelated" not in proofs[0].text

    def test_wrapped_prose_line_does_not_open_a_block(self):
        text = ("Theorem 4. Let x be a thing. The proof uses\n"
                "Lemma 3 together with the fact.\n\nLemma 3. Stuff.\n")
        nodes, *_ = parse_text_structure(text)
        assert [n.label for n in nodes] == ["theorem:4", "lemma:3"]
        assert "together" in nodes[0].text

    def test_slugify_keeps_unicode_letters(self):
        assert slugify("α-algebra") == "α-algebra"
        assert slugify("Hölder inequality") == "hölder-inequality"
        assert slugify("σ-finite") == "σ-finite"


class TestDotLabels:
    def test_label_starting_with_angle_bracket_is_quoted(self):
        from knowtex.core.data import NodeInfo
        n = NodeInfo(env="definition", label="d", index=0, snippet="", pos=0,
                     pos_end=0, display_name="<x, y> pairs")
        dot = build_dot([n], [], {"definition": {}}, add_legend=True)
        assert 'label="<x, y> pairs"' in dot
        assert "label=<<TABLE" in dot      # the legend stays HTML

    def test_micro_view_draws_ghost_neighbours(self):
        from knowtex.core.data import NodeInfo
        a = NodeInfo(env="thm", label="a", index=0, snippet="", pos=0, pos_end=0, display_name="a")
        b = NodeInfo(env="thm", label="b", index=1, snippet="", pos=0, pos_end=0, display_name="b")
        c = NodeInfo(env="thm", label="c", index=2, snippet="", pos=0, pos_end=0, display_name="c")
        edges = [DependencyEdge("a", "b", "x", "proof", "D1")]
        dot = build_dot([a, b, c], edges, {"thm": {}},
                        section_assignments={"a": "S1", "b": "S2", "c": "S2"},
                        view_mode="micro", micro_section="S1", add_legend=False)
        assert '"a" [' in dot and '"b" [' in dot and '"c" [' not in dot
        assert "(external) b" in dot
        assert '"a" -> "b"' in dot


class TestWebApi:
    def test_scan_reads_keyword_text_as_markdown(self):
        import json
        from knowtex import webapi
        res = json.loads(webapi.scan("Definition 2.1. A group is a set.\n", "auto"))
        assert res["ok"] and res["format"] == "markdown" and res["node_count"] == 1

    def test_build_defaults_match_the_cli(self):
        import json
        from knowtex import webapi
        full = json.loads(webapi.build(MD_DOC, "markdown", json.dumps({"tred": False})))
        red = json.loads(webapi.build(MD_DOC, "markdown", "{}"))
        assert full["ok"] and red["ok"]
        assert {e["rule"] for e in red["edges"]} & {"D4", "D1"}   # definitions defaulted
        assert len(red["edges"]) <= len(full["edges"])
        assert red["dot"].startswith("digraph")

    def test_empty_include_means_no_nodes(self):
        import json
        from knowtex import webapi
        res = json.loads(webapi.build(MD_DOC, "markdown", json.dumps({"include": []})))
        assert res["ok"] and res["nodes"] == [] and res["edges"] == []


class TestCli:
    def test_json_and_dot_output(self, tmp_path):
        import json
        from knowtex.cli import main
        src = tmp_path / "notes.md"
        src.write_text(MD_DOC, encoding="utf-8")
        out = tmp_path / "out.json"
        dot = tmp_path / "out.dot"
        assert main([str(src), "--json", str(out), "--dot", str(dot), "--quiet"]) == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["format"] == "markdown"
        assert {n["label"] for n in data["nodes"]} >= {"definition:1.1", "theorem:1.3"}
        assert any(e["rule"] == "D1" for e in data["edges"])
        assert dot.read_text(encoding="utf-8").startswith("digraph")

    def test_no_tred_keeps_more_edges(self, tmp_path):
        import json
        from knowtex.cli import main
        src = tmp_path / "notes.md"
        src.write_text(MD_DOC, encoding="utf-8")
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        main([str(src), "--json", str(a), "--quiet"])
        main([str(src), "--json", str(b), "--quiet", "--no-tred"])
        assert len(json.loads(a.read_text())["edges"]) <= len(json.loads(b.read_text())["edges"])


class TestFolderInput:
    def test_folder_is_read_in_name_order_with_blank_lines(self, tmp_path):
        from knowtex.core.formats import markdown_files, read_markdown_files
        (tmp_path / "b.md").write_text("---\n title: beta\n---\nUses alpha.", encoding="utf-8")
        (tmp_path / "a.md").write_text("---\n title: alpha\n---\nFirst.", encoding="utf-8")   # no final newline
        (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
        files = markdown_files(str(tmp_path))
        assert [f.rsplit("/", 1)[-1] for f in files] == ["a.md", "b.md"]
        text = read_markdown_files(files)
        nodes, nbi, ltn, proofs, envs = parse_text_structure(text)
        assert [n.label for n in nodes] == ["definition:alpha", "definition:beta"]

    def test_unordered_d4_matches_backwards(self):
        text = "---\n title: abelian group\n---\nA group whose operation commutes.\n\n---\n title: group\n---\nA set with an operation.\n"
        nodes, nbi, ltn, proofs, envs = parse_text_structure(text)
        ordered = {(e.source, e.target) for e in run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"})}
        free = {(e.source, e.target) for e in run_inference(nodes, nbi, ltn, proofs, definition_envs={"definition"}, ordered=False)}
        assert ("definition:group", "definition:abelian-group") not in ordered   # group is defined later
        assert ("definition:group", "definition:abelian-group") in free


# ----------------------------------------------------------------------
# Web API (page + local server) and in-memory project expansion
# ----------------------------------------------------------------------

BOOK = r"""\documentclass{book}
\begin{document}
\chapter{One}
\begin{definition}\label{d1} A \emph{gizmo} is a thing. \end{definition}
\begin{theorem}\label{t1} Every gizmo is fine. \end{theorem}
\begin{proof} By \ref{d1}. \end{proof}
\chapter{Two}
\begin{lemma}\label{l1} A gizmo, see \ref{t1}. \end{lemma}
\begin{corollary}\label{c1} Uses \ref{l1}. \end{corollary}
\end{document}
"""


class TestWebApiFull:
    def _j(self, s):
        import json
        return json.loads(s)

    def test_structure_lists_chapters(self):
        from knowtex import webapi
        st = self._j(webapi.structure(BOOK, "latex"))
        assert st["ok"] and st["doc_class"] == "book" and st["range_type"] == "chapter"
        assert [r["title"] for r in st["ranges"]] == ["One", "Two"]

    def test_scan_restricted_to_ranges(self):
        import json
        from knowtex import webapi
        sc = self._j(webapi.scan(BOOK, "latex", json.dumps({"ranges": [1]})))
        assert {n["label"] for n in sc["nodes"]} == {"l1", "c1"}
        assert sc["sections"] == ["Two"]

    def test_micro_view_marks_ghosts(self):
        import json
        from knowtex import webapi
        b = self._j(webapi.build(BOOK, "latex", json.dumps({"micro_section": "Two", "tred": False})))
        labels = {n["label"]: n["ghost"] for n in b["nodes"]}
        assert labels["l1"] is False and labels["c1"] is False
        assert labels["t1"] is True                      # l1 -> ref t1: drawn as external
        assert b["edge_total"] >= len(b["edges"])

    def test_manual_mode_and_added_edges(self):
        import json
        from knowtex import webapi
        b = self._j(webapi.build(BOOK, "latex", json.dumps({"mode": "manual"})))
        assert b["ok"] and b["mode"] == "manual" and b["edges"] == []
        b = self._j(webapi.build(BOOK, "latex", json.dumps({"mode": "manual", "added": [["d1", "c1", "manual", "proof"]]})))
        assert [(e["source"], e["target"], e["rule"]) for e in b["edges"]] == [("d1", "c1", "manual")]

    def test_removed_edge(self):
        import json
        from knowtex import webapi
        full = self._j(webapi.build(BOOK, "latex", "{}"))
        keys = {(e["source"], e["target"]) for e in full["edges"]}
        assert ("d1", "t1") in keys                      # D1 through the proof
        less = self._j(webapi.build(BOOK, "latex", json.dumps({"removed": [["d1", "t1"]]})))
        assert ("d1", "t1") not in {(e["source"], e["target"]) for e in less["edges"]}

    def test_expand_from_files(self):
        import json
        from knowtex import webapi
        r = self._j(webapi.expand(json.dumps({"main.tex": "A\\input{ch/a}", "ch/a.tex": "B\\input{ch/c}", "ch/c.tex": "C"}), "main.tex"))
        assert r["ok"] and r["chars"] == 3 and r["notes"] == [] and r["id"].startswith("doc:")
        assert "text" not in r                                # the page works with the id
        assert webapi._docs[r["id"]].text == "ABC"
        r = self._j(webapi.expand(json.dumps({"main.tex": "A\\input{missing}"}), "main.tex"))
        assert r["ok"] and any("missing file" in n for n in r["notes"])

    def test_load_then_steps_by_id(self):
        """The page's flow: load stores the text, structure lists the
        chapters, scan parses, build infers; snippets come on demand."""
        import json
        from knowtex import webapi
        webapi._docs.clear()                                  # other tests stored BOOK already
        r = self._j(webapi.load(BOOK, "latex"))
        assert r["ok"] and r["chars"] == len(BOOK)
        doc = r["id"]
        D = webapi._docs[doc]
        st = self._j(webapi.structure(doc, "latex"))
        assert [x["title"] for x in st["ranges"]] == ["One", "Two"]
        assert D.parses == {}                                 # structure does not parse
        sc = self._j(webapi.scan(doc, "latex", json.dumps({"ranges": [0]})))
        assert sc["ok"] and {n["label"] for n in sc["nodes"]} == {"d1", "t1"}
        assert all("snippet" not in n for n in sc["nodes"])
        assert list(D.parses) == [(0,)] and D.parses[(0,)].edge_cache == {}   # scan infers nothing
        b = self._j(webapi.build(doc, "latex", json.dumps({"ranges": [0]})))
        assert b["ok"] and [(e["source"], e["target"]) for e in b["edges"]] == [("d1", "t1")]
        assert len(D.parses) == 1                             # build reused the scan's parse
        sn = self._j(webapi.snippet(doc, "latex", "t1", json.dumps({"ranges": [0]})))
        assert sn["ok"] and sn["snippet"].startswith("\\begin{theorem}")
        assert not self._j(webapi.snippet(doc, "latex", "nope", json.dumps({"ranges": [0]})))["ok"]
        bad = self._j(webapi.scan("doc:0000000000000000", "latex"))
        assert not bad["ok"] and "load it again" in bad["error"]

    def test_build_reuses_inferred_edges(self):
        """Display options and edge edits do not rerun the rules."""
        import json
        from knowtex import webapi
        from knowtex.deps import infer
        webapi._docs.clear()
        doc = self._j(webapi.load(BOOK, "latex"))["id"]
        calls = []
        orig = infer.run_inference
        webapi.run_inference = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
        try:
            webapi.build(doc, "latex", "{}")
            webapi.build(doc, "latex", json.dumps({"legend": False, "tred": False}))
            webapi.build(doc, "latex", json.dumps({"removed": [["d1", "t1"]]}))
            webapi.build(doc, "latex", json.dumps({"micro_section": "Two", "rankdir": "LR"}))
            assert len(calls) == 1
            webapi.build(doc, "latex", json.dumps({"include": ["theorem", "lemma"]}))
            assert len(calls) == 2                            # a different graph
        finally:
            webapi.run_inference = orig


class TestLocalServer:
    def test_page_and_api(self):
        import json, threading, http.client
        from http.server import ThreadingHTTPServer
        from knowtex.serve import Handler
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        httpd.verbose = False
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            port = httpd.server_address[1]
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", "/"); r = c.getresponse(); body = r.read().decode()
            assert r.status == 200 and "window.KNOWTEX_LOCAL" in body and "<title>" in body
            c.request("GET", "/api/ping"); r = c.getresponse(); ping = json.loads(r.read())
            assert ping["ok"] and set(ping["capabilities"]) == {"png", "tex", "svg"}
            c.request("GET", "/vendor/d3.min.js"); r = c.getresponse(); r.read()
            assert r.status == 200
            c.request("POST", "/api/scan", body=json.dumps({"args": [MD_DOC, "markdown", "{}"]}),
                      headers={"Content-Type": "application/json"})
            r = c.getresponse(); sc = json.loads(r.read())
            assert sc["ok"] and sc["node_count"] == 4
            c.request("POST", "/api/build", body=json.dumps({"args": [MD_DOC, "markdown", "{}"]}),
                      headers={"Content-Type": "application/json",
                               "Origin": f"http://localhost:{port}",
                               "Sec-Fetch-Site": "same-origin"})
            r = c.getresponse(); b = json.loads(r.read())
            assert b["ok"] and b["dot"].startswith("digraph")
            c.request("GET", "/nope"); r = c.getresponse(); r.read()
            assert r.status == 404
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_refuses_cross_site_requests(self):
        """Another site open in the same browser must not drive the API:
        a foreign Origin, a cross-site Sec-Fetch-Site, a non-JSON body (the
        "simple request" a form or text/plain fetch sends without a CORS
        preflight) and a foreign Host (DNS rebinding) are all refused."""
        import json, threading, http.client
        from http.server import ThreadingHTTPServer
        from knowtex.serve import Handler
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        httpd.verbose = False
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            port = httpd.server_address[1]
            body = json.dumps({"args": [MD_DOC, "markdown", "{}"]})
            dot = json.dumps({"dot": "digraph { a -> b }", "format": "png"})

            def post(path, data, **hdrs):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.request("POST", path, body=data, headers=hdrs)
                r = c.getresponse(); out = r.read(); c.close()
                return r.status, out

            # an evil page: Origin and Sec-Fetch-Site set by the browser
            st, out = post("/api/scan", body, **{"Content-Type": "application/json",
                                                 "Origin": "https://evil.example",
                                                 "Sec-Fetch-Site": "cross-site"})
            assert st == 403 and not json.loads(out)["ok"]
            st, _ = post("/api/export", dot, **{"Content-Type": "application/json",
                                                "Origin": "https://evil.example"})
            assert st == 403
            # a "simple" cross-site POST: no preflight, text/plain body
            st, _ = post("/api/scan", body, **{"Content-Type": "text/plain",
                                               "Origin": "https://evil.example"})
            assert st == 403
            st, _ = post("/api/scan", body, **{"Content-Type": "text/plain"})
            assert st == 403
            # DNS rebinding: Host names another site
            st, _ = post("/api/scan", body, **{"Content-Type": "application/json",
                                               "Host": "evil.example"})
            assert st == 403
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", "/", headers={"Host": "evil.example"}); r = c.getresponse(); r.read()
            assert r.status == 403
            # oversized or non-object bodies
            st, _ = post("/api/scan", "[]", **{"Content-Type": "application/json"})
            assert st == 400
            # the page itself still works
            st, out = post("/api/scan", body, **{"Content-Type": "application/json",
                                                 "Origin": f"http://127.0.0.1:{port}",
                                                 "Sec-Fetch-Site": "same-origin"})
            assert st == 200 and json.loads(out)["node_count"] == 4
        finally:
            httpd.shutdown(); httpd.server_close()
