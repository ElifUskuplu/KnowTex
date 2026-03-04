"""Regex patterns, skip sets, and named constants used across the project."""

import re

# ============================================================
# Environment name matchers
# ============================================================

PROOF_ALIAS_RX = re.compile(r"^(proof|pr|pf|prf|pfof|pfoftheorem)$", re.I)
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

# D3: explicit proof target, e.g. \begin{proof}[Proof of Theorem \ref{thm:X}]
PROOF_OF_REF_RX = re.compile(
    r"\\begin\{(?:proof|pf|pr|prf)\}\s*\[.*?\\(?:ref|Cref|cref)\{([^}]+)\}.*?\]",
    re.I | re.S,
)

# ============================================================
# File inclusion patterns
# ============================================================

INPUT_BRACED_RX = re.compile(r"\\input\s*\{([^}]+)\}")
INPUT_SPACEFORM_RX = re.compile(r"\\input\s+([^\s%]+)")
INCLUDE_RX = re.compile(r"\\include\s*\{([^}]+)\}")
INCLUDEONLY_RX = re.compile(r"\\includeonly\s*\{([^}]*)\}")
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

ENV_BEGIN_RX = re.compile(r"\\begin\{([^}]+)\}")

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
})

# ============================================================
# GUI and rendering constants
# ============================================================

ZOOM_MIN = 0.05
ZOOM_MAX = 8.0
ZOOM_STEP_IN = 1.111111
ZOOM_STEP_OUT = 0.9
ZOOM_FIT_MARGIN = 0.95

EPSILON = 1e-12
SNIPPET_MAX_DISPLAY_LEN = 1000
CLICK_DRAG_THRESHOLD = 4  # pixels
PREVIEW_DPI = "96"
EXPORT_DPI = "150"

SHAPE_OPTIONS = [
    "ellipse", "circle", "doublecircle", "box", "diamond",
    "triangle", "pentagon", "hexagon", "octagon",
]
PRESET_COLORS = [
    "Blue", "Purple", "DimGray", "SkyBlue", "Lavender", "White",
    "Red", "Green", "Orange", "Yellow", "Pink", "Cyan", "Black",
]

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
# LaTeX-to-plaintext stripping patterns
# ============================================================

MATH_INLINE_RX = re.compile(r"\$[^$]+\$")
MATH_DISPLAY_RX = re.compile(r"\\\[.+?\\\]", re.S)
MATH_PAREN_RX = re.compile(r"\\\(.+?\\\)", re.S)
INDEX_NTN_RX = re.compile(r"\\(?:index|ntn)\{[^}]*\}")
LATEX_CMD_RX = re.compile(r"\\[a-zA-Z@]+\*?")
SPECIAL_CHARS_RX = re.compile(r"[{}~^_&$#%]")
