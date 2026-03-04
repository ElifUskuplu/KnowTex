"""Utility functions: path handling, comment stripping, geometry helpers."""

import os
import re

from knowtex.core.constants import COMMENT_RX, EPSILON


def is_within_project(abs_path, project_dir):
    """Check whether abs_path is inside project_dir (safer than startswith)."""
    from pathlib import Path
    try:
        Path(abs_path).relative_to(project_dir)
        return True
    except ValueError:
        return False


def strip_comments(text):
    """Remove LaTeX comments (% and everything after, unless escaped).

    Handles the ``\\\\%`` case (line-break followed by comment) by
    temporarily shielding ``\\\\`` tokens before applying the regex.
    """
    text = text.replace("\\\\", "\x00DBLBS\x00")
    text = re.sub(COMMENT_RX, lambda m: m.group(1), text)
    return text.replace("\x00DBLBS\x00", "\\\\")


def strip_subfile_wrapper(text):
    """Remove documentclass, preamble, and begin/end document from a
    subfiles-package file, returning only the body content."""
    begin_m = re.search(r"\\begin\s*\{document\}", text)
    if begin_m:
        text = text[begin_m.end():]
    end_m = re.search(r"\\end\s*\{document\}", text)
    if end_m:
        text = text[:end_m.start()]
    return text


def normalize_index_term(raw):
    """Normalize a raw \\index{...} content string for matching.

    1. Strip modifiers after first | (textbf, see, seealso, etc.)
    2. Handle sort keys (@): use part before @ for each !-segment
    3. Preserve hierarchy (!)
    4. Lowercase and strip whitespace
    """
    pipe_pos = raw.find("|")
    if pipe_pos >= 0:
        raw = raw[:pipe_pos]
    segments = raw.split("!")
    normalized = []
    for seg in segments:
        seg = seg.strip()
        at_pos = seg.find("@")
        if at_pos >= 0:
            seg = seg[:at_pos].strip()
        seg = " ".join(seg.split())
        if seg:
            normalized.append(seg.lower())
    return "!".join(normalized)


def ensure_tex_ext(path):
    """Add .tex extension if path has no extension."""
    return path if os.path.splitext(path)[1] else path + ".tex"


def norm_join(base_dir, rel):
    """Join paths and normalize."""
    return os.path.normpath(os.path.join(base_dir, rel))


def point_in_poly(x, y, poly):
    """Determine if point (x, y) lies inside polygon using ray casting."""
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and \
                    (x < (xj - xi) * (y - yi) / (yj - yi + EPSILON) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside
