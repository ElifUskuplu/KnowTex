"""Inference engine: D1-D4 and H1-H4 rules.

Applies deterministic and heuristic rules to infer dependency edges
from \\ref/\\Cref/\\eqref cross-references and structural patterns.
"""

import re
from collections import defaultdict

from knowtex.core.constants import (
    REF_RX, EQREF_RX, EMPH_RX,
    PROOF_BEGIN_STRIP_RX, PROOF_END_STRIP_RX,
    COROLLARY_RX, H2_TARGET_RX, LEMMA_RX,
    H3_MAX_GAP,
)
from knowtex.core.data import DependencyEdge
from knowtex.deps.term_extraction import (
    _strip_latex_to_words, _stem, _stem_words,
    _contains_phrase,
    build_defined_term_registry,
)


def run_inference(nodes, node_by_index, label_to_node, proofs,
                  index_registry=None, definition_envs=None):
    """Apply D1-D4 and H2-H3 rules, plus H4 if index_registry is provided."""
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

        proof_snippet = p.snippet
        inner = proof_snippet
        begin_match = PROOF_BEGIN_STRIP_RX.match(inner)
        if begin_match:
            inner = inner[begin_match.end():]
        end_match = PROOF_END_STRIP_RX.search(inner)
        if end_match:
            inner = inner[:end_match.start()]

        for rx in (REF_RX, EQREF_RX):
            for rm in rx.finditer(inner):
                ref_label = rm.group(1).strip()
                if ref_label in all_labels and ref_label != parent_label:
                    add_edge(ref_label, parent_label,
                             "deterministic", "proof", "D1")

    # --- D2: Process each statement ---
    for ni in nodes:
        snippet = ni.snippet
        label = ni.label

        for rm in REF_RX.finditer(snippet):
            ref_label = rm.group(1).strip()
            if ref_label in all_labels and ref_label != label:
                add_edge(ref_label, label,
                         "deterministic", "statement", "D2")

        for rm in EQREF_RX.finditer(snippet):
            ref_label = rm.group(1).strip()
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
            words = _strip_latex_to_words(ni.snippet)
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
            for m in EMPH_RX.finditer(ni.snippet):
                raw = m.group(1).strip()
                if raw.startswith("\\") or raw.startswith("$"):
                    continue
                cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\{[^}]*\})?", " ", raw)
                cleaned = cleaned.replace("{", " ").replace("}", " ")
                cleaned = " ".join(cleaned.split()).strip().lower()
                if len(cleaned) >= 2:
                    words = cleaned.split()
                    defined.add(tuple(_stem(w) for w in words))
            node_defined_terms[ni.label] = defined

        for ni in nodes:
            target_stem_set = node_stem_set_cache[ni.label]
            target_stem_seq = node_stem_seq_cache[ni.label]
            target_defined = node_defined_terms.get(ni.label, set())
            for src_label, src_index, _raw_term, term_stems in term_registry:
                if src_label == ni.label:
                    continue
                if src_index >= ni.index:
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
        has_ref = (bool(REF_RX.search(ni.snippet))
                   or bool(EQREF_RX.search(ni.snippet)))
        if has_ref:
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
            words = _strip_latex_to_words(ni.snippet)
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
