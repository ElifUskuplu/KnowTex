#!/usr/bin/env python3
"""Tests of the headless pipeline (``knowtex/pipeline.py``), the command
line built on it, and the regression baselines of the paper's datasets.

Run with:  pytest tests/test_pipeline.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))   # repository root
sys.path.insert(0, os.path.dirname(__file__))                    # tests/ (regression.py)

from knowtex.pipeline import (  # noqa: E402
    PipelineConfig, load_input, run_pipeline, default_definition_envs,
)

DOC = r"""
\documentclass{article}
\begin{document}
\section{One}
\begin{definition}\label{d1}
A \emph{widget} is a gadget with a handle.
\end{definition}
\begin{remark}\label{r1}
Widgets are everywhere.
\end{remark}
\begin{theorem}\label{t1}
Every widget has a handle.
\end{theorem}
\begin{proof}
By Definition~\ref{d1}.
\end{proof}
\begin{lemma}\label{l1}
A widget with two handles is a bucket.
\end{lemma}
\begin{theorem}\label{t2}
Buckets exist.
\end{theorem}
\begin{proof}
See Remark~\ref{r1} and Lemma~\ref{l1}.
\end{proof}
\end{document}
"""


def pairs(result):
    return sorted((e.source, e.target) for e in result.edges)


class TestPipelineConfig:
    def test_defaults(self):
        c = PipelineConfig()
        assert c.mode == "infer" and c.include is None and c.definition_envs is None
        assert c.ordered and c.resolve_cycles and c.tred

    def test_from_dict_reads_page_keys_and_ignores_display_keys(self):
        c = PipelineConfig.from_dict({
            "mode": "manual", "include": ["thm", "defn"], "definition_envs": ["defn"],
            "ordered": 0, "tred": False,
            "ranges": [0], "removed": [["a", "b"]], "colors": {}, "legend": False,
        })
        assert c.mode == "manual"
        assert c.include == frozenset({"thm", "defn"})
        assert c.definition_envs == frozenset({"defn"})
        assert c.ordered is False and c.tred is False and c.resolve_cycles is True

    def test_unknown_key_is_an_error(self):
        with pytest.raises(KeyError):
            PipelineConfig.from_dict({"includes": ["thm"]})
        c = PipelineConfig.from_dict({"includes": ["thm"]}, strict=False)
        assert c.include is None

    def test_bad_mode(self):
        with pytest.raises(ValueError):
            PipelineConfig(mode="auto")

    def test_roundtrip(self):
        c = PipelineConfig(include={"b", "a"}, ordered=False)
        d = c.to_dict()
        assert d["include"] == ["a", "b"] and d["ordered"] is False
        assert PipelineConfig.from_dict(d) == c

    def test_default_definition_envs(self):
        assert default_definition_envs({"theorem", "definition", "defn", "remark"}) == {
            "definition", "defn"}


class TestRunPipeline:
    def test_all_kinds(self):
        r = run_pipeline(DOC, "latex")
        assert r.fmt == "latex"
        assert len(r.nodes) == len(r.all_nodes) == 5
        assert ("d1", "t1") in pairs(r)          # D1 via \ref in the proof
        assert ("r1", "t2") in pairs(r)          # D1 to a remark
        assert ("l1", "t2") in pairs(r)
        assert set(r.envs) == {"definition", "remark", "theorem", "lemma"}

    def test_include_drops_edges_of_excluded_kinds(self):
        cfg = PipelineConfig(include={"definition", "theorem", "lemma"})
        r = run_pipeline(DOC, "latex", cfg)
        assert [n.env for n in r.nodes] == ["definition", "theorem", "lemma", "theorem"]
        assert len(r.all_nodes) == 5             # the remark is parsed, not drawn
        assert ("r1", "t2") not in pairs(r)
        assert ("d1", "t1") in pairs(r) and ("l1", "t2") in pairs(r)

    def test_selection_does_not_change_labels(self):
        """Numeric fallback labels are assigned at parse time, over every
        statement, so a selection cannot renumber them."""
        doc = DOC.replace("\\label{r1}", "").replace("Remark~\\ref{r1} and ", "")
        full = run_pipeline(doc, "latex")
        part = run_pipeline(doc, "latex", PipelineConfig(include={"remark", "theorem"}))
        remark_full = [n.label for n in full.nodes if n.env == "remark"]
        remark_part = [n.label for n in part.nodes if n.env == "remark"]
        assert remark_full == remark_part and remark_full[0].startswith("remark:")

    def test_tred_and_cycles_flags(self):
        r_tred = run_pipeline(DOC, "latex")
        r_all = run_pipeline(DOC, "latex", PipelineConfig(tred=False))
        assert set(pairs(r_tred)) <= set(pairs(r_all))
        assert r_all.config.tred is False and r_tred.cycles == set()

    def test_manual_mode(self):
        doc = DOC.replace("\\begin{proof}\nBy Definition~\\ref{d1}.",
                          "\\begin{proof}\\uses{d1}\nBy Definition~\\ref{d1}.")
        r = run_pipeline(doc, "latex", PipelineConfig(mode="manual"))
        assert pairs(r) == [("d1", "t1")]
        assert all(e.rule == "manual" for e in r.edges)

    def test_edge_rows_are_sorted_tuples(self):
        rows = run_pipeline(DOC, "latex").edge_rows()
        assert rows == sorted(rows)
        assert all(len(row) == 5 for row in rows)
        assert rows[0][2] in ("D1", "D2", "D4", "H2", "H3", "H4")


class TestLoadInput:
    def test_latex_file_is_expanded(self, tmp_path):
        (tmp_path / "part.tex").write_text("\\begin{theorem}\\label{t}\nA.\n\\end{theorem}\n")
        main = tmp_path / "main.tex"
        main.write_text("\\documentclass{article}\\begin{document}\\input{part}\\end{document}\n")
        text, fmt, coll = load_input(str(main))
        assert fmt == "latex" and not coll and "\\label{t}" in text

    def test_folder_is_a_glossary_without_order(self, tmp_path):
        (tmp_path / "b.md").write_text("---\ntitle: ring\n---\nA ring is an abelian group with a product.\n")
        (tmp_path / "a.md").write_text("---\ntitle: abelian group\n---\nA commutative group.\n")
        text, fmt, coll = load_input(str(tmp_path))
        assert fmt == "markdown" and coll
        assert text.index("abelian group") < text.index("title: ring")   # file-name order
        r = run_pipeline(text, fmt, PipelineConfig(ordered=False, definition_envs={"definition"}))
        assert [n.env for n in r.nodes] == ["definition", "definition"]
        assert pairs(r) == [("definition:abelian-group", "definition:ring")]

    def test_empty_folder(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_input(str(tmp_path))


class TestCli:
    def _run(self, argv):
        from knowtex.cli import main
        assert main(argv) == 0

    def test_json_matches_pipeline(self, tmp_path):
        src = tmp_path / "doc.tex"
        src.write_text(DOC)
        out = tmp_path / "out.json"
        self._run([str(src), "--quiet", "--json", str(out)])
        j = json.loads(out.read_text())
        want = run_pipeline(DOC, "latex")
        assert sorted((e["source"], e["target"]) for e in j["edges"]) == pairs(want)
        assert j["config"] == PipelineConfig().to_dict()

    def test_include_env_flag_and_config_file(self, tmp_path):
        src = tmp_path / "doc.tex"
        src.write_text(DOC)
        cfg = tmp_path / "run.json"
        cfg.write_text(json.dumps({"include": ["definition", "theorem", "lemma"], "legend": False}))
        out1, out2 = tmp_path / "a.json", tmp_path / "b.json"
        self._run([str(src), "--quiet", "--config", str(cfg), "--json", str(out1)])
        self._run([str(src), "--quiet", "--include-env", "definition", "--include-env", "theorem",
                   "--include-env", "lemma", "--json", str(out2)])
        a, b = json.loads(out1.read_text()), json.loads(out2.read_text())
        assert a["edges"] == b["edges"]
        assert a["config"]["include"] == ["definition", "lemma", "theorem"]
        assert all(e["source"] != "r1" for e in a["edges"])

    def test_flag_overrides_config_file(self, tmp_path):
        src = tmp_path / "doc.tex"
        src.write_text(DOC)
        cfg = tmp_path / "run.json"
        cfg.write_text(json.dumps({"tred": True, "mode": "infer"}))
        out = tmp_path / "a.json"
        self._run([str(src), "--quiet", "--config", str(cfg), "--no-tred", "--json", str(out)])
        assert json.loads(out.read_text())["config"]["tred"] is False

    def test_markdown_input_json_and_dot(self, tmp_path):
        """A Markdown file goes through the same path: labels from the
        numbering, D1 from a textual reference, DOT written."""
        md = ("## Definition 1.1\nA **group** is a set with an operation.\n\n"
              "## Theorem 1.3\nEvery group has an identity.\n\n"
              "Proof. By Definition 1.1. QED\n")
        src = tmp_path / "notes.md"
        src.write_text(md, encoding="utf-8")
        out, dot = tmp_path / "out.json", tmp_path / "out.dot"
        self._run([str(src), "--quiet", "--json", str(out), "--dot", str(dot)])
        j = json.loads(out.read_text())
        assert j["format"] == "markdown"
        assert {n["label"] for n in j["nodes"]} == {"definition:1.1", "theorem:1.3"}
        assert [(e["source"], e["target"], e["rule"]) for e in j["edges"]] == [
            ("definition:1.1", "theorem:1.3", "D1")]
        assert dot.read_text().startswith("digraph")

    def test_folder_defaults_to_unordered(self, tmp_path):
        (tmp_path / "a.md").write_text("---\ntitle: ring\n---\nA group with a product.\n")
        (tmp_path / "b.md").write_text("---\ntitle: group\n---\nA set with an operation.\n")
        out = tmp_path / "o.json"
        self._run([str(tmp_path), "--quiet", "--json", str(out)])
        j = json.loads(out.read_text())
        assert j["config"]["ordered"] is False
        assert [(e["source"], e["target"]) for e in j["edges"]] == [
            ("definition:group", "definition:ring")]      # b.md comes after a.md


class TestWebApiMatchesPipeline:
    def _edges(self, raw):
        j = json.loads(raw)
        assert j["ok"], j.get("error")
        return sorted((e["source"], e["target"]) for e in j["edges"])

    def test_build_equals_run_pipeline(self):
        from knowtex import webapi
        webapi._docs.clear()
        for cfg in ({}, {"include": ["definition", "theorem", "lemma"]},
                    {"tred": False}, {"mode": "manual"}):
            page = self._edges(webapi.build(DOC, "latex", json.dumps(cfg)))
            assert page == pairs(run_pipeline(DOC, "latex", PipelineConfig.from_dict(cfg))), cfg


@pytest.fixture(scope="module")
def results():
    """Every paper dataset run once, keyed by (dataset, mode)."""
    import regression
    return {(r["dataset"], r["mode"]): r for r in regression.check(out=lambda *a: None)}


class TestPaperDatasets:
    """The four datasets of the article reproduce the graphs stored next
    to their sources (see tests/regression.py and tests/datasets.py).
    A dataset whose input is missing (the Chicago corpus must be
    downloaded) is skipped, not failed."""

    def test_every_baseline_holds(self, results):
        bad = {k: (v["status"], v["added"][:3], v["removed"][:3])
               for k, v in results.items() if v["status"] not in ("ok", "skipped")}
        assert not bad, bad

    @pytest.mark.parametrize("key,nodes,edges", [
        (("group_theory", "infer"), 42, 68),
        (("group_theory", "manual"), 42, 64),
        (("bct", "infer"), 45, 65),
        (("bct", "manual"), 45, 61),
        (("pfr", "infer"), 218, 344),
        (("pfr", "manual"), 218, 403),
        (("chicago", "infer"), 611, 2256),
    ])
    def test_counts_of_the_paper(self, results, key, nodes, edges):
        r = results[key]
        if r["status"] == "skipped":
            pytest.skip(r.get("note", "input missing"))
        assert (r["nodes"], r["edges"]) == (nodes, edges)
