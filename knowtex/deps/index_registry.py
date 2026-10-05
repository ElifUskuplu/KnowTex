"""Index registry for the index/emphasis inference rule (H4).

``term_to_first_node`` maps each normalized ``\\index{}`` or emphasized
(``\\emph``, ``\\textit``, ``\\textbf``, ``\\demph``) term to the label of
the first node, in document order, whose statement contains it.
Built for LaTeX input only.
"""

from knowtex.core.constants import INDEX_RX, INDEX_SEE_RX
from knowtex.core.utils import normalize_index_term
from knowtex.deps.term_extraction import _extract_emph_terms


def build_index_registry(nodes, proofs, tex):
    """Build data structures for index-based inference rules.

    Returns dict with keys:
      - term_to_first_node: normalized_term -> label of first node containing it
      - hierarchy_links: list of (normalized_parent, normalized_child)
    """
    # Build |see{} alias map and resolve transitive chains
    see_aliases = {}
    for m in INDEX_SEE_RX.finditer(tex):
        alias = normalize_index_term(m.group(1))
        canonical = normalize_index_term(m.group(2))
        if alias and canonical and alias != canonical:
            see_aliases[alias] = canonical

    def resolve(term):
        visited = {term}
        current = term
        while current in see_aliases:
            nxt = see_aliases[current]
            if nxt in visited:
                break
            visited.add(nxt)
            current = nxt
        return current

    # One pass over the nodes in document order so that an \emph in an
    # early node beats an \index in a later one.  A cross-reference entry
    # (\index{x|see{y}}) is not a use of y.
    term_to_first_node = {}
    all_hierarchy_terms = set()
    for ni in nodes:
        for m in INDEX_RX.finditer(ni.snippet):
            raw = m.group(1)
            if "|see" in raw.lower():
                continue
            norm = resolve(normalize_index_term(raw))
            if norm:
                term_to_first_node.setdefault(norm, ni.label)
                all_hierarchy_terms.add(norm)
        for et in _extract_emph_terms(ni.snippet):
            term_to_first_node.setdefault(et, ni.label)

    for p in proofs:
        for m in INDEX_RX.finditer(p.snippet):
            raw = m.group(1)
            if "|see" in raw.lower():
                continue
            norm = resolve(normalize_index_term(raw))
            if norm:
                all_hierarchy_terms.add(norm)

    # Parent-child links from hierarchical terms (e.g. algebra!group)
    hierarchy_links = []
    for term in all_hierarchy_terms:
        if "!" not in term:
            continue
        parts = term.split("!")
        for i in range(1, len(parts)):
            parent = "!".join(parts[:i])
            child = "!".join(parts[:i + 1])
            hierarchy_links.append((parent, child))

    return {
        "term_to_first_node": term_to_first_node,
        "hierarchy_links": hierarchy_links,
    }
