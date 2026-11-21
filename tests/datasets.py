"""The four case studies of the article: how each graph is built and what
its gold standard is.  Used by ``tests/regression.py`` (rebuild the graphs
and compare them with the DOT files stored next to the sources) and by
``tests/test_report.py`` (the evaluation against the gold standards).

    group_theory   example/                  Case Study 1
    bct            BCT-condensed/            Case Study 2
    chicago        chicago_notes/            Case Study 3 (downloaded by its benchmark script)
    pfr            Polynomial-Freiman-Ruzsa/ Case Study 4

``modes`` lists the runs (infer, manual) with the input file and the
pipeline options that change the edges; ``dot`` is the stored graph the
regression check compares with (Chicago has no graph file: its 2,256
edges are kept as a CSV in ``chicago_notes/data/results/``).  ``gold``
names the gold standard for ``knowtex.evaluation``; ``aliases`` rename
gold labels to the labels the inferred graph uses (the article's
"normalized" numbers).
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASETS = [
    {
        "name": "group_theory",
        "modes": {
            "infer": {"path": "example/group_theory.tex", "format": "latex",
                      "config": {"mode": "infer"},
                      "dot": "example/group_theory-knowtex/inferred-graph-groups.dot"},
            "manual": {"path": "example/group_theory_with_uses.tex", "format": "latex",
                       "config": {"mode": "manual"},
                       "dot": "example/group_theory_with_uses-knowtex/manual-graph-groups.dot"},
        },
        # the \uses{} annotations of group_theory_with_uses.tex; same labels as the source
        "gold": {"type": "manual", "mode": "manual"},
    },
    {
        "name": "bct",
        # the source has 171 theorem-like environments; the article keeps the 45
        # definitions, constructions, theorems, propositions, lemmas and corollaries
        "modes": {
            "infer": {"path": "BCT-condensed/BCT-knowtex/tex-files/BCT.tex", "format": "latex",
                      "config": {"mode": "infer",
                                 "include": ["defn", "constn", "thm", "propn", "lemma", "cor"]},
                      "dot": "BCT-condensed/BCT-knowtex/inferred-graph-BCT.dot"},
            "manual": {"path": "BCT-condensed/BCT_with_uses-knowtex/tex-files/BCT_with_uses.tex",
                       "format": "latex",
                       "config": {"mode": "manual",
                                  "include": ["defn", "constn", "thm", "propn", "lemma", "cor"]},
                       "dot": "BCT-condensed/BCT_with_uses-knowtex/manual-graph-BCT.dot"},
        },
        # the annotated copy labels ten definitions differently from what infer
        # mode derives from the original source
        "gold": {"type": "manual", "mode": "manual", "aliases": {
            "defn:hom-func": "defn:co-rep",
            "defn:repr-func": "defn:representable",
            "defn:contra-repr-func": "defn:representation",
            "defn:Hom-func-unified": "defn:hom-set",
            "defn:contra-hom-func": "defn:145",
            "defn:contra-yon-emb": "defn:144",
            "defn:full-faithful": "defn:faithful",
            "defn:nat-trans": "defn:natural-transformation",
            "defn:ess-surj": "defn:essentially-surjective-on-objects",
            "defn:comma-cat": "defn:comma-category",
        }},
    },
    {
        "name": "chicago",
        # the MathGloss Chicago glossary, 611 Markdown files read as one glossary with no
        # reading order; every entry is a definition; edges evaluated before transitive
        # reduction, as in chicago_benchmark.py
        "baseline_dir": "chicago_notes/data/results",
        "modes": {
            "infer": {"path": "chicago_notes/data/chicago_md", "format": "markdown",
                      "config": {"mode": "infer", "ordered": False,
                                 "definition_envs": ["definition"], "tred": False}},
        },
        # the inter-definition hyperlinks (chicago_benchmark.build_ground_truth)
        "gold": {"type": "chicago_hyperlinks"},
    },
    {
        "name": "pfr",
        "modes": {
            "infer": {"path": "Polynomial-Freiman-Ruzsa/pfr_without_uses/print.tex", "format": "latex",
                      "config": {"mode": "infer"},
                      "dot": "Polynomial-Freiman-Ruzsa/pfr_without_uses/print-knowtex/pfr_infer_graph.dot"},
            "manual": {"path": "Polynomial-Freiman-Ruzsa/pfr_with_uses/print.tex", "format": "latex",
                       "config": {"mode": "manual"},
                       "dot": "Polynomial-Freiman-Ruzsa/pfr_with_uses/print-knowtex/pfr_manual_graph.dot"},
        },
        # the dependency graph of the project's Lean Blueprint site (Graphviz SVG in the
        # HTML page; dashed = statement-level); two lemmas carry two \label{} commands
        "gold": {"type": "blueprint_html", "path": "Polynomial-Freiman-Ruzsa/Dependency-graph.html",
                 "aliases": {"rhoMinus_nonneg": "rhominus-nonneg", "rho_of_uniform": "rho-init"}},
    },
]


def load_configs(names=None):
    """The dataset configs, sorted by name (or only the ones in *names*)."""
    configs = [dict(c) for c in DATASETS if not names or c["name"] in names]
    configs.sort(key=lambda c: c["name"])
    if names:
        missing = set(names) - {c["name"] for c in configs}
        if missing:
            raise KeyError(f"no config for: {', '.join(sorted(missing))}")
    return configs
