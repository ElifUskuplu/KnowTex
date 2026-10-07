"""Term extraction and stemming for the D4 and H4 rules.

Works on two kinds of node:

* LaTeX nodes (``NodeInfo.text is None``): words, defined terms and
  references are derived from the LaTeX ``snippet`` with regexes.
* Nodes from the Markdown front-end: the front-end has
  already filled ``text``, ``defined_terms`` and ``refs``; nothing is
  parsed here.
"""

import re

from knowtex.core.constants import (
    EMPH_RX, INDEX_RX, MATH_INLINE_RX, MATH_DISPLAY_RX, MATH_PAREN_RX,
    MATH_DOLLAR_DISPLAY_RX,
    INDEX_NTN_RX, LATEX_CMD_RX, SPECIAL_CHARS_RX,
)
from knowtex.core.utils import normalize_index_term

# PyStemmer (C extension) is fast; snowballstemmer is the same algorithm
# in pure Python and is what the browser build (Pyodide) uses.
try:
    import Stemmer as _PyStemmer
    _stemmer = _PyStemmer.Stemmer("english")
except ImportError:  # pragma: no cover - depends on the environment
    import snowballstemmer as _snowball
    _stemmer = _snowball.stemmer("english")

# A document's vocabulary is small next to its word count, so every word
# is stemmed once and looked up afterwards.
_stem_cache = {}


def _stem(word):
    try:
        return _stem_cache[word]
    except KeyError:
        s = _stem_cache[word] = _stemmer.stemWord(word.lower())
        return s


def _stem_words(text_words):
    cache = _stem_cache
    out = []
    for w in text_words:
        try:
            out.append(cache[w])
        except KeyError:
            s = cache[w] = _stemmer.stemWord(w.lower())
            out.append(s)
    return out


class WordCache:
    """Words and stems of nodes, computed once per node.

    One instance lives with a parse (``webapi``) so that the D4 and H4
    rules, the cycle resolution and every later build reuse the same
    lists instead of re-reading the LaTeX of every statement.
    """

    def __init__(self):
        self._words = {}
        self._stems = {}

    def words(self, node):
        try:
            return self._words[node.label]
        except KeyError:
            w = self._words[node.label] = node_words(node)
            return w

    def stems(self, node):
        try:
            return self._stems[node.label]
        except KeyError:
            s = self._stems[node.label] = _stem_words(self.words(node))
            return s


def _contains_phrase(stem_sequence, phrase_stems):
    """Check if *phrase_stems* appears as a contiguous subsequence in
    *stem_sequence*."""
    n = len(phrase_stems)
    if n == 0:
        return False
    first = phrase_stems[0]
    if n == 1:
        return first in stem_sequence
    phrase_stems = list(phrase_stems)
    i = 0
    last = len(stem_sequence) - n
    try:
        while i <= last:
            i = stem_sequence.index(first, i)       # C-speed jump to the next start
            if stem_sequence[i:i + n] == phrase_stems:
                return True
            i += 1
    except ValueError:
        pass
    return False


def words_from_plain(text):
    """Tokenize markup-free text into lowercase words.

    A word ending in ".", ",", "?" or ";" is followed by a "." boundary
    token so that phrase matching cannot span a sentence or clause.
    """
    words = []
    for w in text.split():
        has_boundary = w[-1] in ".,?;" if w else False
        w = w.strip(".,;:!?()[]\"'")
        if len(w) >= 2:
            words.append(w.lower())
        if has_boundary:
            words.append(".")
    return words


def _strip_latex_to_words(snippet):
    """Strip LaTeX commands and math mode from a snippet, return lowercase words."""
    text = snippet
    text = MATH_DOLLAR_DISPLAY_RX.sub(" ", text)
    text = MATH_INLINE_RX.sub(" ", text)
    text = MATH_DISPLAY_RX.sub(" ", text)
    text = MATH_PAREN_RX.sub(" ", text)
    text = INDEX_NTN_RX.sub(" ", text)
    text = LATEX_CMD_RX.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = SPECIAL_CHARS_RX.sub(" ", text)
    return words_from_plain(text)


def node_words(node):
    """Lowercase word list of a node or proof, whatever its source format."""
    text = getattr(node, "text", None)
    if text is not None:
        return words_from_plain(text)
    return _strip_latex_to_words(node.snippet)


def _clean_emph(raw):
    raw = raw.strip()
    if raw.startswith("\\") or raw.startswith("$"):
        return ""
    cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\{[^}]*\})?", " ", raw)
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    return " ".join(cleaned.split()).strip()


def _extract_emph_terms(snippet):
    """Extract normalized terms from \\emph{...}, \\textit{...}, \\textbf{...}.

    Returns list of lowercase, whitespace-collapsed term strings.
    Skips terms that are purely LaTeX commands or math.
    """
    terms = []
    for m in EMPH_RX.finditer(snippet):
        cleaned = _clean_emph(m.group(1)).lower()
        if len(cleaned) >= 2:
            terms.append(cleaned)
    return terms


def _extract_index_terms(snippet):
    terms = []
    for idx_m in INDEX_RX.finditer(snippet):
        raw_idx = idx_m.group(1)
        if "|see" in raw_idx.lower():
            continue
        norm = normalize_index_term(raw_idx)
        if not norm or len(norm) < 2:
            continue
        if "!" in norm:
            parts = norm.split("!")
            norm = " ".join(reversed(parts))
        terms.append(norm)
    return terms


def defined_term_strings(node):
    """Raw defined-term strings of a node (case preserved, deduplicated).

    LaTeX nodes: \\emph{}/\\textit{}/\\textbf{}/\\demph{} then \\index{}.
    Other nodes: whatever the front-end stored in ``defined_terms``.
    """
    stored = getattr(node, "defined_terms", None)
    if stored is not None:
        raw_terms = [" ".join(t.split()) for t in stored]
    else:
        raw_terms = []
        for m in EMPH_RX.finditer(node.snippet):
            cleaned = _clean_emph(m.group(1))
            if len(cleaned) >= 2:
                raw_terms.append(cleaned)
        raw_terms.extend(_extract_index_terms(node.snippet))

    out, seen = [], set()
    for t in raw_terms:
        lower = t.lower()
        if len(lower) < 2 or lower in seen:
            continue
        seen.add(lower)
        out.append(t)
    return out


def redefinition_term_strings(node):
    """Terms a node introduces *itself*, used by D4 to skip an edge from
    an earlier definition of the same term.

    LaTeX nodes: \\emph{}/\\textit{}/\\textbf{}/\\demph{} only.  An
    \\index{} entry marks usage, not a (re)definition, so it must not block
    the edge.  Other nodes: their ``defined_terms``.
    """
    stored = getattr(node, "defined_terms", None)
    if stored is not None:
        return [" ".join(t.split()) for t in stored]
    out = []
    for m in EMPH_RX.finditer(node.snippet):
        cleaned = _clean_emph(m.group(1))
        if len(cleaned) >= 2:
            out.append(cleaned)
    return out


def extract_defined_terms(node):
    """Extract defined terms from a definition environment.

    Returns a list of (raw_term, stems) tuples.
    """
    terms = []
    for raw in defined_term_strings(node):
        words = raw.lower().split()
        if not words:
            continue
        stems = _stem_words(words)
        if not all(len(s) >= 2 for s in stems):
            continue
        terms.append((raw, stems))
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
