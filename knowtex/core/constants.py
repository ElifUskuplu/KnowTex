"""Regex patterns, skip sets, and named constants used across the project."""

import re

# ============================================================
# Environment name matchers
# ============================================================

PROOF_ALIASES = ("proof", "pr", "pf", "prf", "pfof", "pfoftheorem")
PROOF_ALIAS_RX = re.compile(r"^(" + "|".join(PROOF_ALIASES) + r")\*?$", re.I)
COROLLARY_RX = re.compile(r"^(corollary|cor|corol|corl)$", re.I)
H2_TARGET_RX = re.compile(
    r"^(theorem|thm|th|thrm|proposition|propn|prop|prp)$", re.I
)
LEMMA_RX = re.compile(r"^(lemma|lem|lm|lma)$", re.I)

# Strip \begin{...}[...] and \end{...} wrappers from proof snippets
PROOF_BEGIN_STRIP_RX = re.compile(r"\\begin\{[^}]+\}(?:\s*\[[^\]]*\])?\s*", re.S)
PROOF_END_STRIP_RX = re.compile(r"\\end\{[^}]+\}\s*$")

# ============================================================
# Content extraction regex
# ============================================================

LABEL_RX = re.compile(r"\\label\{([^}]+)\}")
USES_RX = re.compile(r"\\uses\{([^}]*)\}")
PROVES_RX = re.compile(r"\\proves\{([^}]*)\}")
REF_RX = re.compile(r"\\(?:ref|Cref|cref)\{([^}]+)\}")
EQREF_RX = re.compile(r"\\eqref\{([^}]+)\}")

INDEX_RX = re.compile(r"\\index\{([^}]+)\}")
INDEX_SEE_RX = re.compile(r"\\index\{([^|}]+)\|see\{([^}]+)\}\}")

EMPH_RX = re.compile(
    r"\\(?:emph|textit|textbf|demph)\{((?:[^{}]|\{[^}]*\})*)\}",
    re.IGNORECASE | re.DOTALL,
)

# D3: explicit proof target(s).  PROOF_HEADER_RX captures the optional
# argument of \begin{proof}[...]; every \ref/\cref/\Cref in it (REF_RX,
# comma lists split) is a target: "Proof of Theorems \ref{a} and \ref{b}"
# attaches the proof to both.  PROOF_OF_REF_RX (first reference only) is
# kept for compatibility.
PROOF_HEADER_RX = re.compile(
    r"\\begin\{(?:" + "|".join(PROOF_ALIASES) + r")\*?\}\s*\[(.*?)\]",
    re.I | re.S,
)
PROOF_OF_REF_RX = re.compile(
    r"\\begin\{(?:" + "|".join(PROOF_ALIASES) + r")\*?\}"
    r"\s*\[.*?\\(?:ref|Cref|cref)\{([^}]+)\}.*?\]",
    re.I | re.S,
)


def split_labels(text):
    """The labels of a comma-separated reference argument
    (``\\cref{a,b}`` or ``\\proves{a, b}``), stripped and non-empty."""
    return [x.strip() for x in text.split(",") if x.strip()]

# ============================================================
# File inclusion patterns
# ============================================================

INPUT_BRACED_RX = re.compile(r"\\input\s*\{([^}]+)\}")
INPUT_SPACEFORM_RX = re.compile(r"\\input\s+([^\s%]+)")
INCLUDE_RX = re.compile(r"\\include\s*\{([^}]+)\}")
# one level of nested braces allowed: \includeonly{a,\ifbool{x}{b}{c},d}
INCLUDEONLY_RX = re.compile(r"\\includeonly\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
IMPORT_RX = re.compile(r"\\import\s*\{([^}]+)\}\s*\{([^}]+)\}")
SUBIMPORT_RX = re.compile(r"\\subimport\s*\{([^}]+)\}\s*\{([^}]+)\}")
SUBFILE_RX = re.compile(r"\\subfile\s*\{([^}]+)\}")
COMMENT_RX = re.compile(r"(^|[^\\])%.*")

# ============================================================
# Structural patterns
# ============================================================

DOCUMENTCLASS_RX = re.compile(
    r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}"
)
CHAPTER_RX = re.compile(
    r"\\chapter\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", re.M
)
SECTION_RX = re.compile(
    r"\\section\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", re.M
)

# ============================================================
# Well-known non-theorem environments to SKIP during scanning
# ============================================================

SKIP_ENVS = frozenset({
    "document", "abstract", "figure", "table", "tabular", "tabularx",
    "enumerate", "itemize", "description", "equation", "equation*",
    "align", "align*", "gather", "gather*", "multline", "multline*",
    "split", "cases", "matrix", "pmatrix", "bmatrix", "vmatrix",
    "array", "minipage", "center", "flushleft", "flushright",
    "quote", "quotation", "verse", "verbatim", "lstlisting", "minted",
    "tikzpicture", "pgfpicture", "picture", "thebibliography",
    "filecontents", "filecontents*", "frame", "block", "columns",
    "column", "beamer", "titlepage", "letter", "scope",
    "tikzcd", "tikzcd*", "cd", "displaymath", "flalign", "flalign*",
    "subequations", "adjustbox", "wrapfigure", "landscape", "sideways",
    "eqnarray", "eqnarray*", "list",
    # inner math / float variants
    "aligned", "alignat", "alignat*", "alignedat", "gathered",
    "smallmatrix", "Bmatrix", "Vmatrix", "dcases", "rcases", "multlined",
    "figure*", "table*", "tabular*", "longtable", "tabu", "sidewaystable",
    "sidewaysfigure", "subfigure", "subtable", "algorithm", "algorithmic",
    "algorithm*", "algorithmic*", "lstlisting*", "comment", "small", "footnotesize",
    "tiny", "large", "Large", "LARGE", "huge", "Huge", "spacing", "singlespace",
    "doublespace", "onehalfspace", "flushright*", "tcolorbox", "mdframed",
    "framed", "shaded", "sloppypar", "samepage", "appendices", "multicols",
    "multicols*", "enumerate*", "itemize*", "description*", "tasks", "verbatim*",
    "xy", "warning", "slogan", "displaytext",
})

# ============================================================
# Inference constants
# ============================================================

# Matches definition-like environment names (auto-checked in config dialog)
DEFN_ENV_RX = re.compile(
    r"^(defn|definition|dfn|def|constn|construction|notation|ntn"
    r"|convention|conv|axiom|ax)$",
    re.IGNORECASE,
)

# Math environments whose \label{} should be ignored during node labelling
INNER_LABEL_ENVS = frozenset({
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "flalign", "flalign*", "subequations",
    "eqnarray", "eqnarray*", "split", "cases",
})

H3_MAX_GAP = 3  # max node gap for H3 lemma->theorem heuristic

# ============================================================
# Default node styles per statement kind (Graphviz)
# ============================================================
# Used by the command line's DOT output.  The web page keeps the same
# table in JavaScript (KIND_STYLE in web/template.html); change both.

DEFAULT_ENV_STYLES = {
    "definition":  {"shape": "box",     "border": "#2A6FA8", "fill": "#DCEBF7"},
    "notation":    {"shape": "box",     "border": "#2A6FA8", "fill": "#DCEBF7"},
    "axiom":       {"shape": "box",     "border": "#2A6FA8", "fill": "#DCEBF7"},
    "theorem":     {"shape": "ellipse", "border": "#B5761A", "fill": "#FBEBC8"},
    "proposition": {"shape": "ellipse", "border": "#6B4CA8", "fill": "#E8E0F4"},
    "lemma":       {"shape": "ellipse", "border": "#2F7D4A", "fill": "#DDF0DC"},
    "corollary":   {"shape": "ellipse", "border": "#A83A62", "fill": "#F5DEE6"},
    "conjecture":  {"shape": "hexagon", "border": "#B5761A", "fill": "#FBEBC8"},
    "claim":       {"shape": "ellipse", "border": "#2F7D4A", "fill": "#DDF0DC"},
    "example":     {"shape": "note",    "border": "#6C7278", "fill": "#EDEEEA"},
    "remark":      {"shape": "note",    "border": "#6C7278", "fill": "#EDEEEA"},
    "default":     {"shape": "ellipse", "border": "#6C7278", "fill": "#EDEEEA"},
}
_STYLE_ALIAS = {"defn": "definition", "def": "definition", "dfn": "definition",
                "thm": "theorem", "prop": "proposition", "propn": "proposition",
                "lem": "lemma", "cor": "corollary", "rem": "remark", "ex": "example",
                "conj": "conjecture", "ntn": "notation", "constn": "definition",
                "construction": "definition"}


def default_env_style(env):
    """The default style dict of a statement kind (a copy)."""
    k = env.lower()
    return dict(DEFAULT_ENV_STYLES.get(k) or DEFAULT_ENV_STYLES.get(_STYLE_ALIAS.get(k, ""))
                or DEFAULT_ENV_STYLES["default"])

# ============================================================
# LaTeX-to-plaintext stripping patterns
# ============================================================

MATH_DOLLAR_DISPLAY_RX = re.compile(r"\$\$.*?\$\$", re.S)  # strip before MATH_INLINE_RX
MATH_INLINE_RX = re.compile(r"\$[^$]+\$")
MATH_DISPLAY_RX = re.compile(r"\\\[.+?\\\]", re.S)
MATH_PAREN_RX = re.compile(r"\\\(.+?\\\)", re.S)
INDEX_NTN_RX = re.compile(r"\\(?:index|ntn)\{[^}]*\}")
LATEX_CMD_RX = re.compile(r"\\[a-zA-Z@]+\*?")
SPECIAL_CHARS_RX = re.compile(r"[{}~^_&$#%]")
