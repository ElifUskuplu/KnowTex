"""Inference engine: D1-D4 and H1-H4 rules.

Applies deterministic and heuristic rules to infer dependency edges
from \\ref/\\cref/\\Cref/\\eqref cross-references (or the ``refs`` a
non-LaTeX front-end resolved), defined-term matching and structural patterns.
"""

import re
from collections import defaultdict

from knowtex.core.cycles import strongly_connected_components
from knowtex.core.constants import (
    REF_RX, EQREF_RX,
    PROOF_BEGIN_STRIP_RX, PROOF_END_STRIP_RX,
    COROLLARY_RX, H2_TARGET_RX, LEMMA_RX,
    H3_MAX_GAP,
)
from knowtex.core.data import DependencyEdge
from knowtex.deps.term_extraction import (
    node_words, redefinition_term_strings, _stem, _stem_words,
    _contains_phrase, extract_defined_terms,
    build_defined_term_registry,
)


def node_refs(node):
    """Labels referenced by a statement node.

    Non-LaTeX front-ends store them in ``refs``; LaTeX nodes are scanned
    for \\ref/\\Cref/\\cref/\\eqref.
    """
    stored = getattr(node, "refs", None)
    if stored is not None:
        return list(stored)
    out = []
    for rx in (REF_RX, EQREF_RX):
        for rm in rx.finditer(node.snippet):
            out.append(rm.group(1).strip())
    return out


def proof_refs(proof):
    """Labels referenced inside a proof body (header excluded)."""
    stored = getattr(proof, "refs", None)
    if stored is not None:
        return list(stored)
    inner = proof.snippet
    begin_match = PROOF_BEGIN_STRIP_RX.match(inner)
    if begin_match:
        inner = inner[begin_match.end():]
    end_match = PROOF_END_STRIP_RX.search(inner)
    if end_match:
        inner = inner[:end_match.start()]
    out = []
    for rx in (REF_RX, EQREF_RX):
        for rm in rx.finditer(inner):
            out.append(rm.group(1).strip())
    return out


def run_inference(nodes, node_by_index, label_to_node, proofs,
                  index_registry=None, definition_envs=None, ordered=True):
    """Apply D1-D4 and H2-H3 rules, plus H4 if index_registry is provided.

    ``ordered=False`` is for several Markdown files loaded together (a
    glossary, one entry per file): the files have no reading order, so
    D4's "the definition comes before the statement that uses the term"
    check is switched off.  Nothing else changes.
    """
    edges = []
    seen = set()

    def add_edge(source, target, edge_type, location, rule):
        """Record that *target* depends on *source* (source -> target)."""
        key = (source, target)
        if key not in seen and source != target:
            seen.add(key)
            edges.append(
                DependencyEdge(source, target, edge_type, location, rule)
            )

    all_labels = set(label_to_node.keys())

    # --- D1: Process each proof ---
    for p in proofs:
        tgt_idx = p.target_node_idx
        if tgt_idx is None:
            continue
        tgt_node = node_by_index.get(tgt_idx)
        if not tgt_node:
            continue
        parent_label = tgt_node.label

        for ref_label in proof_refs(p):
            if ref_label in all_labels and ref_label != parent_label:
                add_edge(ref_label, parent_label,
                         "deterministic", "proof", "D1")

    # --- D2: Process each statement ---
    for ni in nodes:
        label = ni.label
        for ref_label in node_refs(ni):
            if ref_label in all_labels and ref_label != label:
                add_edge(ref_label, label,
                         "deterministic", "statement", "D2")

    # --- D4: Defined-term matching ---
    if definition_envs:
        term_registry = build_defined_term_registry(nodes, definition_envs)

        # For single-word terms a set lookup suffices; for multi-word
        # terms we need ordered stem sequences for phrase matching.
        node_stem_set_cache = {}
        node_stem_seq_cache = {}
        for ni in nodes:
            words = node_words(ni)
            stems = _stem_words(words)
            node_stem_set_cache[ni.label] = set(stems)
            node_stem_seq_cache[ni.label] = stems

        # Build set of full stem tuples each node defines via emph.
        # We store tuples of stems (not individual words) so that
        # "\demph{contravariant functor}" does NOT block the single-word
        # term "functor" coming from another definition.
        node_defined_terms = {}
        for ni in nodes:
            defined = set()
            for raw in redefinition_term_strings(ni):
                words = raw.lower().split()
                if words:
                    defined.add(tuple(_stem(w) for w in words))
            node_defined_terms[ni.label] = defined

        for ni in nodes:
            target_stem_set = node_stem_set_cache[ni.label]
            target_stem_seq = node_stem_seq_cache[ni.label]
            target_defined = node_defined_terms.get(ni.label, set())
            for src_label, src_index, _raw_term, term_stems in term_registry:
                if src_label == ni.label:
                    continue
                if ordered and src_index >= ni.index:
                    continue
                if tuple(term_stems) in target_defined:
                    continue
                # Single-word: set membership; multi-word: contiguous phrase match
                if len(term_stems) == 1:
                    matched = term_stems[0] in target_stem_set
                else:
                    matched = _contains_phrase(target_stem_seq, term_stems)
                if matched:
                    add_edge(src_label, ni.label,
                             "deterministic", "statement", "D4")

    # --- H2: Corollary without \\ref -> nearest preceding theorem ---
    for ni in nodes:
        if not COROLLARY_RX.fullmatch(ni.env):
            continue
        if node_refs(ni):
            continue
        already_has_dep = any(
            e.target == ni.label and e.rule != "D4"
            for e in edges
        )
        if already_has_dep:
            continue

        best_idx = None
        for other in nodes:
            if other.index >= ni.index:
                break
            if H2_TARGET_RX.fullmatch(other.env):
                best_idx = other.index

        if best_idx is not None:
            src_node = node_by_index[best_idx]
            add_edge(src_node.label, ni.label,
                     "heuristic", "inferred", "H2")

    # --- H3: Lemma -> next theorem/proposition ---
    for i, ni in enumerate(nodes):
        if not LEMMA_RX.fullmatch(ni.env):
            continue

        next_thm_node = None
        for j in range(i + 1, min(i + 1 + H3_MAX_GAP, len(nodes))):
            other = nodes[j]
            if H2_TARGET_RX.fullmatch(other.env):
                next_thm_node = other
                break

        if next_thm_node is None:
            continue

        already_linked = any(
            e.source == ni.label and e.target == next_thm_node.label
            for e in edges
        )
        if already_linked:
            continue

        add_edge(ni.label, next_thm_node.label,
                 "heuristic", "inferred", "H3")

    # --- Index-based rule (H4) ---
    if index_registry is not None:
        t2fn = index_registry["term_to_first_node"]

        defn_labels = set()  # skip terms already handled by D4
        if definition_envs:
            for ni in nodes:
                if ni.env in definition_envs:
                    defn_labels.add(ni.label)

        # H4: Index term matching (longest-match-first)
        # For single-word terms a set lookup suffices; for multi-word
        # terms we use contiguous phrase matching to avoid false positives.
        node_words_set_cache = {}
        node_stem_seq_cache_h4 = {}
        for ni in nodes:
            words = node_words(ni)
            node_words_set_cache[ni.label] = set(words)
            node_stem_seq_cache_h4[ni.label] = _stem_words(words)

        sorted_terms = []
        for term, first_label in t2fn.items():
            if "," in term:
                continue
            if first_label in defn_labels:
                continue  # D4 already handles terms from definition envs
            if "!" in term:
                parts = term.split("!")
                multi_word = " ".join(reversed(parts))
                sorted_terms.append((multi_word, first_label))
            else:
                sorted_terms.append((term, first_label))
        sorted_terms.sort(key=lambda x: len(x[0]), reverse=True)

        node_consumed_words = defaultdict(set)

        for term, first_label in sorted_terms:
            first_intro_node = label_to_node.get(first_label)
            if not first_intro_node:
                continue
            term_words = term.lower().split()
            term_stems = _stem_words(term_words)

            for ni in nodes:
                if ni.label == first_label:
                    continue
                if ni.index <= first_intro_node.index:
                    continue

                if len(term_stems) == 1:
                    # Single-word: set membership with consumed tracking
                    words = node_words_set_cache[ni.label]
                    consumed = node_consumed_words[ni.label]
                    ts = term_stems[0]
                    found = [w for w in words
                             if _stem(w) == ts and w not in consumed]
                    if found:
                        add_edge(first_label, ni.label,
                                 "heuristic", "inferred", "H4")
                        consumed.add(found[0])
                else:
                    # Multi-word: contiguous phrase match
                    stem_seq = node_stem_seq_cache_h4[ni.label]
                    if _contains_phrase(stem_seq, term_stems):
                        add_edge(first_label, ni.label,
                                 "heuristic", "inferred", "H4")

    return edges


# ---------------------------------------------------------------------------
# Cycle resolution (a pass over the finished edge list; no rule is changed)
# ---------------------------------------------------------------------------

def _plural_eq(word, term_word):
    """True when *word* is *term_word* up to an English plural ending."""
    if word == term_word:
        return True
    if word in (term_word + "s", term_word + "es"):
        return True
    if term_word in (word + "s", word + "es"):
        return True
    if word.endswith("ies") and term_word == word[:-3] + "y":
        return True
    if term_word.endswith("ies") and word == term_word[:-3] + "y":
        return True
    return False


def _surface_match(term_words, target_words):
    """Does the term occur in the target's words with the same surface
    form (plural endings aside), not just the same stems?"""
    n = len(term_words)
    if n == 0:
        return False
    for i in range(len(target_words) - n + 1):
        if all(_plural_eq(target_words[i + j], term_words[j]) for j in range(n)):
            return True
    return False


EXPLICIT_RULES = frozenset({"D1", "D2", "D3", "manual"})


def resolve_cycles(edges, nodes=None, breakable=("D4",), explicit=EXPLICIT_RULES):
    """Drop the weakest term-match edges until every remaining cycle is
    made of explicit edges only.  Returns ``(kept, dropped)``.

    D4 reads the *words* of a statement; D1/D2/D3 and manual edges read
    what the author wrote (``\\ref``, hyperlinks, ``\\uses``).  When the
    two disagree about the direction of a dependency, the author wins.
    The pass never removes an edge whose rule is not in *breakable* and
    never changes how any rule matches; it only decides which of the
    edges already found survive when they close a cycle.  Edges of the
    heuristic rules (H2, H3, H4) are neither *explicit* nor *breakable*:
    they pass through untouched and play no part in the graph below, so
    a heuristic guess can never cost a D4 edge.

    1. A breakable edge ``s -> t`` is dropped when ``t`` already reaches
       ``s`` through explicit edges: the term match contradicts the
       explicit cross-references.
    2. While a strongly connected component of the explicit and
       breakable edges still contains a breakable edge, the one with the
       least evidence is dropped and the components are recomputed.
       Evidence, weakest first:
       (a) the term occurs in the target only through its stem
           ("function" for *functional*), never with its own surface
           form, when *nodes* are given so the text can be re-read;
       (b) the source term matched in many statements (a hub word such
           as *closed* or *group*).
       Ties fall back to the edge key, so the result is deterministic.

    Cycles made entirely of explicit edges are left alone; they are the
    author's and ``find_cycles`` still reports them.
    """
    breakable = set(breakable)
    strong = [e for e in edges if e.rule in explicit]
    weak = [e for e in edges if e.rule in breakable]
    if not weak:
        return list(edges), []

    # --- step 1: term matches that contradict explicit references
    strong_adj = defaultdict(set)
    for e in strong:
        strong_adj[e.source].add(e.target)

    def reaches(start, goal):
        seen, stack = {start}, [start]
        while stack:
            x = stack.pop()
            if x == goal:
                return True
            for y in strong_adj[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return False

    dropped = []
    survivors = []
    for e in weak:
        if reaches(e.target, e.source):
            dropped.append(e)
        else:
            survivors.append(e)

    # --- step 2: evidence ranking inside the remaining components
    hub = defaultdict(int)
    for e in weak:
        hub[e.source] += 1

    surface = {}
    if nodes is not None:
        by_label = {n.label: n for n in nodes}
        words_cache = {}
        terms_cache = {}
        for e in survivors:
            src, tgt = by_label.get(e.source), by_label.get(e.target)
            if src is None or tgt is None:
                surface[e.key()] = False
                continue
            if e.target not in words_cache:
                words_cache[e.target] = node_words(tgt)
            if e.source not in terms_cache:
                terms_cache[e.source] = [raw.lower().split()
                                         for raw, _ in extract_defined_terms(src)]
            tw = words_cache[e.target]
            surface[e.key()] = any(_surface_match(t, tw) for t in terms_cache[e.source])

    def score(e):
        return (surface.get(e.key(), False), -hub[e.source], e.key())

    current = {e.key(): e for e in survivors}
    while True:
        sccs, adj = strongly_connected_components(strong + list(current.values()))
        candidates = []
        for scc in sccs:
            if len(scc) < 2:
                continue
            for src in scc:
                for tgt in adj[src]:
                    if tgt in scc and (src, tgt) in current:
                        candidates.append(current[(src, tgt)])
        if not candidates:
            break
        worst = min(candidates, key=score)
        dropped.append(worst)
        del current[worst.key()]

    kept = [e for e in edges if e.rule not in breakable or e.key() in current]
    return kept, dropped
