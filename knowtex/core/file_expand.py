"""Multi-file LaTeX project expansion.

Recursively resolves \\input, \\include, \\import, \\subimport, and \\subfile
commands into a single string, with path-traversal prevention.
"""

import os
import re

from knowtex.core.constants import (
    INPUT_BRACED_RX, INPUT_SPACEFORM_RX,
    INCLUDE_RX, INCLUDEONLY_RX,
    IMPORT_RX, SUBIMPORT_RX, SUBFILE_RX,
)
from knowtex.core.utils import (
    is_within_project, strip_comments, strip_subfile_wrapper,
    ensure_tex_ext, norm_join,
)


def load_and_expand(main_path):
    """Recursively expand all include commands and return complete document text."""
    main_path = os.path.realpath(main_path)
    project_dir = os.path.realpath(os.path.dirname(main_path))

    def read_file(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(p, "r", encoding="latin-1") as f:
                return f.read()

    return _expand(main_path, project_dir, read_file, os.path.exists)


def expand_from_files(main_name, files):
    """Expand a LaTeX project given in memory (the browser build).

    ``files`` maps project-relative paths (``"chapters/ch1.tex"``) to their
    text; ``main_name`` is the main file's key.  The same expansion rules
    as ``load_and_expand`` apply, with the project root at ``/``.
    """
    norm = {os.path.normpath("/" + k.replace("\\", "/")): v for k, v in files.items()}
    main_path = os.path.normpath("/" + main_name.replace("\\", "/"))
    if main_path not in norm:
        raise FileNotFoundError(main_name)

    def read_file(p):
        try:
            return norm[p]
        except KeyError:
            raise FileNotFoundError(p)

    return _expand(main_path, "/", read_file, lambda p: p in norm,
                   realpath=os.path.normpath)


def _expand(main_path, project_dir, read_file, exists, realpath=os.path.realpath):
    """Shared expansion: *read_file(path)* returns text or raises
    FileNotFoundError, *exists(path)* says whether a path is readable."""
    visited = set()

    def _include_key(name):
        """\\include{gr/gr1}, \\includeonly{gr/gr1.tex} and "./gr/gr1" name the
        same file: compare normalised paths without the extension."""
        name = name.strip().replace("\\", "/")
        if name.lower().endswith(".tex"):
            name = name[:-4]
        return os.path.normpath(name)

    def collect_includeonly(text):
        """The file names listed in \\includeonly{...}.  Names inside a
        conditional such as \\ifbool{..}{a}{b,c} are all kept; the macro
        names themselves are not file names and never match anything."""
        incs = set()
        for m in INCLUDEONLY_RX.finditer(strip_comments(text)):
            for x in re.split(r"[,{}]", m.group(1)):
                x = x.strip()
                if x and not x.startswith("\\"):
                    incs.add(_include_key(x))
        return incs

    main_text = read_file(main_path)
    includeonly = collect_includeonly(main_text)

    def expand_text(text, current_dir):
        """Process all include/input/subfile commands in the given text."""
        def expand_match(rel_path, override_dir=None, subfile=False):
            rel = rel_path.strip()
            inc_path = ensure_tex_ext(norm_join(override_dir or current_dir, rel))
            if not exists(inc_path) and override_dir is None:
                # LaTeX resolves \input paths relative to the main document,
                # not the including file; try that before giving up.
                alt = ensure_tex_ext(norm_join(project_dir, rel))
                if exists(alt):
                    inc_path = alt
            inc_dir = os.path.dirname(inc_path)
            return expand_file(inc_path, inc_dir, subfile=subfile)

        def repl_import(m):
            inc_dir = norm_join(current_dir, m.group(1))
            return expand_match(m.group(2), override_dir=inc_dir)

        text = IMPORT_RX.sub(repl_import, text)
        text = SUBIMPORT_RX.sub(repl_import, text)

        text = INPUT_BRACED_RX.sub(lambda m: expand_match(m.group(1)), text)
        text = INPUT_SPACEFORM_RX.sub(lambda m: expand_match(m.group(1)), text)

        def repl_include(m):
            name = m.group(1).strip()
            if includeonly and _include_key(name) not in includeonly:
                return f"% [knowtex] skipped by \\includeonly: {name}\n"
            return expand_match(name)

        text = INCLUDE_RX.sub(repl_include, text)

        text = SUBFILE_RX.sub(lambda m: expand_match(m.group(1), subfile=True), text)

        return text

    def expand_file(path, current_dir, subfile=False):
        """Read a file, strip comments (and the \\documentclass{subfiles}
        wrapper when *subfile*), then expand include commands."""
        abs_path = realpath(path)
        if not is_within_project(abs_path, project_dir) and abs_path != main_path:
            return f"% [knowtex] blocked path outside project: {abs_path}\n"
        if abs_path in visited:
            return ""
        visited.add(abs_path)

        try:
            raw = read_file(abs_path)
        except FileNotFoundError:
            return f"% [knowtex] missing file: {abs_path}\n"

        text = strip_comments(raw)
        if subfile:
            text = strip_subfile_wrapper(text)
        return expand_text(text, current_dir)

    return expand_file(main_path, project_dir)
