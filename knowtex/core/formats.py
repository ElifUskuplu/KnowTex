"""Input format detection and dispatch.

KnowTeX accepts two input formats:

* ``latex``    -- a full document or a pasted fragment (pylatexenc parser)
* ``markdown`` -- headings, ``**bold**`` defined terms, ``[text](#label)`` links,
                  and keyword lines such as "Definition 2.1." / "Proof."

``parse_document`` returns the same tuple for every format, so the
inference rules never need to know where the text came from.
"""

import re

_LATEX_RX = re.compile(r"\\(?:begin|documentclass|section|chapter|label|ref)\s*\{")
_MATH_RX = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$|\\\[.*?\\\]|\\\(.*?\\\)", re.S)

FORMATS = ("latex", "markdown")

FORMAT_BY_SUFFIX = {
    ".tex": "latex", ".ltx": "latex",
    ".md": "markdown", ".markdown": "markdown",
}


MARKDOWN_SUFFIXES = (".md", ".markdown")


def markdown_files(folder):
    """The Markdown files of *folder*, sorted by name (no recursion)."""
    import os
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder))
            if f.lower().endswith(MARKDOWN_SUFFIXES)]


def read_markdown_files(paths):
    """Read several Markdown files as one document.

    The files are joined with a blank line between them, so a file that
    does not end in a newline cannot swallow the next file's heading or
    front matter.  Such a set of files has no reading order: callers pass
    ``ordered=False`` to ``run_inference``.
    """
    parts = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            parts.append(fh.read().strip("\n"))
    return "\n\n".join(parts) + "\n"


def format_for_path(path, default="latex"):
    """Input format implied by a file name's extension."""
    import os
    return FORMAT_BY_SUFFIX.get(os.path.splitext(str(path))[1].lower(), default)


def detect_format(text):
    """Guess the input format of *text*: "latex" or "markdown".

    LaTeX commands inside math (``$\\begin{bmatrix}…$``) occur in Markdown
    too, so only commands outside math count as LaTeX evidence.
    """
    if _LATEX_RX.search(_MATH_RX.sub(" ", text)):
        return "latex"
    return "markdown"


def parse_document(text, fmt=None, **kwargs):
    """Parse *text* in the given (or detected) format.

    Returns: (fmt, nodes, node_by_index, label_to_node, proofs, discovered_envs)
    """
    if fmt is None or fmt == "auto":
        fmt = detect_format(text)
    if fmt == "latex":
        from knowtex.core.parser import parse_latex_structure
        result = parse_latex_structure(text)
    elif fmt == "markdown":
        from knowtex.core.text_parser import parse_text_structure
        result = parse_text_structure(text, **kwargs)
    else:
        raise ValueError(f"unknown format: {fmt!r} (expected one of {FORMATS})")
    return (fmt,) + tuple(result)
