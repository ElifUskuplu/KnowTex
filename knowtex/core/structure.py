"""Document structure detection: document class, chapter/section ranges, section assignment."""

from knowtex.core.constants import DOCUMENTCLASS_RX, CHAPTER_RX, SECTION_RX


def detect_doc_class(tex):
    """Detect document class from \\documentclass{...}.

    Returns 'book' for book/report/memoir/scrbook/scrreprt, 'article' otherwise.
    """
    m = DOCUMENTCLASS_RX.search(tex)
    if not m:
        return "article"
    cls = m.group(1).strip().lower()
    if cls in ("book", "report", "memoir", "scrbook", "scrreprt"):
        return "book"
    return "article"


def find_chapter_ranges(tex):
    """Find all \\chapter{...} commands with their text ranges.

    Returns list of {title, start, end} dicts.
    """
    matches = list(CHAPTER_RX.finditer(tex))
    if not matches:
        return []
    chapters = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if (i + 1) < len(matches) else len(tex)
        chapters.append({"title": title, "start": start, "end": end})
    return chapters


def find_section_ranges(tex):
    """Find all \\section{...} commands with their text ranges.

    Returns list of {title, start, end} dicts.
    """
    matches = list(SECTION_RX.finditer(tex))
    if not matches:
        return []
    sections = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if (i + 1) < len(matches) else len(tex)
        sections.append({"title": title, "start": start, "end": end})
    return sections


def assign_sections(nodes, ranges):
    """Assign each node to its chapter/section based on character position.

    Returns {node_label -> section_title}.
    """
    assignments = {}
    for ni in nodes:
        for rng in ranges:
            if rng["start"] <= ni.pos < rng["end"]:
                assignments[ni.label] = rng["title"]
                break
        else:
            assignments[ni.label] = "(ungrouped)"
    return assignments
