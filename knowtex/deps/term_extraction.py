"""Term extraction and stemming utilities for inference rules D4 and H4."""

import re

from knowtex.core.constants import (
    EMPH_RX, INDEX_RX,
    MATH_INLINE_RX, MATH_DISPLAY_RX, MATH_PAREN_RX,
    INDEX_NTN_RX, LATEX_CMD_RX, SPECIAL_CHARS_RX,
)
from knowtex.core.utils import normalize_index_term

import Stemmer as PyStemmer

_stemmer = PyStemmer.Stemmer("english")


def _stem(word):
    """Stem a single word using Snowball stemmer."""
    return _stemmer.stemWord(word.lower())


def _stem_words(text_words):
    """Stem a list of words. Returns list of stems."""
    return [_stem(w) for w in text_words]


def _contains_phrase(stem_sequence, phrase_stems):
    """Check if *phrase_stems* appears as a contiguous subsequence in
    *stem_sequence*.  Both arguments are lists of stemmed words."""
    plen = len(phrase_stems)
    if plen == 0:
        return False
    for i in range(len(stem_sequence) - plen + 1):
        if stem_sequence[i:i + plen] == phrase_stems:
            return True
    return False


def _strip_latex_to_words(snippet):
    """Strip LaTeX commands and math mode from a snippet, return lowercase words."""
    text = snippet
    text = MATH_INLINE_RX.sub(" ", text)
    text = MATH_DISPLAY_RX.sub(" ", text)
    text = MATH_PAREN_RX.sub(" ", text)
    text = INDEX_NTN_RX.sub(" ", text)
    text = LATEX_CMD_RX.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = SPECIAL_CHARS_RX.sub(" ", text)
    words = []
    for w in text.split():
        # Preserve sentence-ending punctuation as a boundary marker
        # so that phrase matching cannot span across sentences.
        has_boundary = w[-1] in ".,?;" if w else False
        w = w.strip(".,;:!?()[]\"'")
        if len(w) >= 2:
            words.append(w.lower())
        if has_boundary:
            words.append(".")
    return words


def _extract_emph_terms(snippet):
    """Extract normalized terms from \\emph{...}, \\textit{...}, \\textbf{...}.

    Returns list of lowercase, whitespace-collapsed term strings.
    Skips terms that are purely LaTeX commands or math.
    """
    terms = []
    for m in EMPH_RX.finditer(snippet):
        raw = m.group(1).strip()
        if raw.startswith("\\") or raw.startswith("$"):
            continue
        cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\{[^}]*\})?", " ", raw)
        cleaned = cleaned.replace("{", " ").replace("}", " ")
        cleaned = " ".join(cleaned.split()).lower().strip()
        if len(cleaned) >= 2:
            terms.append(cleaned)
    return terms


def extract_defined_terms(node):
    """Extract defined terms from a definition environment's snippet.

    Returns a list of (raw_term, stems) tuples.
    """
    terms = []
    seen = set()
    for m in EMPH_RX.finditer(node.snippet):
        raw = m.group(1).strip()
        if raw.startswith("\\") or raw.startswith("$") or len(raw) < 2:
            continue
        cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\{[^}]*\})?", " ", raw)
        cleaned = cleaned.replace("{", " ").replace("}", " ")
        cleaned = " ".join(cleaned.split()).strip()
        if len(cleaned) < 2:
            continue

        lower = cleaned.lower()
        if lower in seen:
            continue
        seen.add(lower)

        words = lower.split()
        if not words:
            continue
        stems = _stem_words(words)
        if not all(len(s) >= 2 for s in stems):
            continue

        terms.append((cleaned, stems))

    # Extract from \index{} entries as well
    for idx_m in INDEX_RX.finditer(node.snippet):
        raw_idx = idx_m.group(1)
        if "|see" in raw_idx.lower():
            continue
        norm = normalize_index_term(raw_idx)
        if not norm or len(norm) < 2:
            continue
        if "!" in norm:
            parts = norm.split("!")
            term_text = " ".join(reversed(parts))
        else:
            term_text = norm
        if term_text in seen:
            continue
        seen.add(term_text)
        words = term_text.split()
        if not words:
            continue
        stems = _stem_words(words)
        if not all(len(s) >= 2 for s in stems):
            continue
        terms.append((term_text, stems))

    return terms


def build_defined_term_registry(nodes, definition_envs):
    """Build a list of defined terms from definition-type environments.

    Only considers nodes whose environment is in definition_envs.
    For each term, only the first-introducing node (by document order) is recorded.

    Returns: list of (source_label, source_index, raw_term, stems)
    """
    registry = []
    seen_terms = set()
    for ni in nodes:
        if ni.env not in definition_envs:
            continue
        for raw_term, rx in extract_defined_terms(ni):
            if raw_term.lower() not in seen_terms:
                seen_terms.add(raw_term.lower())
                registry.append((ni.label, ni.index, raw_term, rx))
    return registry
