"""Index registry for index-based inference rule (H4)."""

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

    # Collect index terms from nodes (first occurrence wins)
    term_to_first_node = {}
    node_index_terms = {}
    all_hierarchy_terms = set()

    for ni in nodes:
        terms = []
        for m in INDEX_RX.finditer(ni.snippet):
            raw = m.group(1)
            norm = resolve(normalize_index_term(raw))
            if norm:
                terms.append(norm)
                if norm not in term_to_first_node:
                    term_to_first_node[norm] = ni.label
                all_hierarchy_terms.add(norm)
        node_index_terms[ni.label] = terms

    # Also collect emphasized terms (\emph, \textit, etc.)
    node_emph_terms = {}
    for ni in nodes:
        eterms = _extract_emph_terms(ni.snippet)
        new_terms = []
        for et in eterms:
            if et not in term_to_first_node:
                term_to_first_node[et] = ni.label
                new_terms.append(et)
            elif term_to_first_node[et] != ni.label:
                new_terms.append(et)
        node_emph_terms[ni.label] = new_terms

    # Collect index terms from proofs
    proof_index_terms = {}
    for p in proofs:
        terms = []
        for m in INDEX_RX.finditer(p.snippet):
            raw = m.group(1)
            norm = resolve(normalize_index_term(raw))
            if norm:
                terms.append(norm)
                all_hierarchy_terms.add(norm)
        proof_index_terms[p.index] = terms

    # Build parent-child links from hierarchical terms (e.g. algebra!group)
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
