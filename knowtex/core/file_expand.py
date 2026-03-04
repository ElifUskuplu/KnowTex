"""Multi-file LaTeX project expansion.

Recursively resolves \\input, \\include, \\import, \\subimport, and \\subfile
commands into a single string, with path-traversal prevention.
"""

import os

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
    visited = set()

    def collect_includeonly(text):
        incs = set()
        for m in INCLUDEONLY_RX.finditer(strip_comments(text)):
            names = [x.strip() for x in m.group(1).split(",") if x.strip()]
            incs.update(names)
        return incs

    def read_file(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(p, "r", encoding="latin-1") as f:
                return f.read()

    main_path = os.path.realpath(main_path)
    project_dir = os.path.realpath(os.path.dirname(main_path))
    main_text = read_file(main_path)
    includeonly = collect_includeonly(main_text)

    def expand_text(text, current_dir):
        """Process all include/input/subfile commands in the given text."""
        def expand_match(rel_path, override_dir=None):
            inc_path = ensure_tex_ext(
                norm_join(override_dir or current_dir, rel_path.strip())
            )
            inc_dir = os.path.dirname(inc_path)
            return expand_file(inc_path, inc_dir)

        def repl_import(m):
            inc_dir = norm_join(current_dir, m.group(1))
            return expand_match(m.group(2), override_dir=inc_dir)

        text = IMPORT_RX.sub(repl_import, text)
        text = SUBIMPORT_RX.sub(repl_import, text)

        text = INPUT_BRACED_RX.sub(lambda m: expand_match(m.group(1)), text)
        text = INPUT_SPACEFORM_RX.sub(lambda m: expand_match(m.group(1)), text)

        def repl_include(m):
            name = m.group(1).strip()
            base_name = os.path.basename(name)
            if includeonly and (base_name not in includeonly):
                return f"% [knowtex] skipped by \\includeonly: {name}\n"
            return expand_match(name)

        text = INCLUDE_RX.sub(repl_include, text)

        def repl_subfile(m):
            rel = m.group(1).strip()
            inc_path = ensure_tex_ext(norm_join(current_dir, rel))
            abs_path = os.path.realpath(inc_path)
            if not is_within_project(abs_path, project_dir):
                return (
                    f"% [knowtex] blocked path outside project: {abs_path}\n"
                )
            if abs_path in visited:
                return ""
            visited.add(abs_path)
            try:
                raw = read_file(abs_path)
            except FileNotFoundError:
                return f"% [knowtex] missing file: {abs_path}\n"
            body = strip_subfile_wrapper(strip_comments(raw))
            inc_dir = os.path.dirname(abs_path)
            return expand_text(body, inc_dir)

        text = SUBFILE_RX.sub(repl_subfile, text)

        return text

    def expand_file(path, current_dir):
        """Read a file, strip comments, then expand include commands."""
        abs_path = os.path.realpath(path)
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
        return expand_text(text, current_dir)

    return expand_file(main_path, project_dir)
