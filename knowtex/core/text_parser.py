"""Markdown front-end (also reads keyword-only text with no Markdown markup).

Produces the same (nodes, node_by_index, label_to_node, proofs,
discovered_envs) tuple as ``parser.parse_latex_structure`` so that the
inference rules run unchanged.  Nothing is converted to LaTeX: the
front-end fills ``NodeInfo.text``, ``defined_terms`` and ``refs``
directly, which is exactly the information the rules need.

Recognized structure
--------------------
Statement blocks start with a keyword header at the beginning of a line::

    Definition 2.1 (Group).  A **group** is ...
    **Theorem 3.** ...
    Lemma. ...
    Proof.  ...  QED / ∎ / □
    Proof of Theorem 2.1. ...

Markdown headings may carry the same keyword (``## Theorem 2.1 (Lagrange)``,
``## Proof``); such a block runs to the next heading.  A heading without a
keyword is a section title.  When the text has no
keyword blocks at all (a glossary such as MathGloss, one heading or one
YAML ``title:`` per entry) every heading becomes a ``definition`` node.

Labels: ``{#label}`` after a header, else ``kind:number``, else
``kind:name``, else ``kind:<first defined term>``, else ``kind:<index>``.

References: ``[text](#label)``, ``[text](.../slug)`` (last path segment
matched against node slugs) and textual "Theorem 2.1" / "Lemma 3"
mentions resolved through the numbering.

Defined terms: ``**bold**``, "quoted" spans, the parenthesized name of a
definition header, the title of a glossary entry, and "called a(n) X".
"""

import re

from knowtex.core.constants import DEFN_ENV_RX
from knowtex.core.data import NodeInfo, ProofInfo

# ------------------------------------------------------------------
# Keyword tables
# ------------------------------------------------------------------

KIND_ALIASES = {
    "definition": ("definition", "defn", "def", "dfn"),
    "theorem": ("theorem", "thm"),
    "lemma": ("lemma", "lem"),
    "proposition": ("proposition", "prop"),
    "corollary": ("corollary", "cor"),
    "remark": ("remark", "rem"),
    "example": ("example", "ex", "examples"),
    "axiom": ("axiom",),
    "notation": ("notation",),
    "convention": ("convention",),
    "conjecture": ("conjecture", "conj"),
    "claim": ("claim",),
    "construction": ("construction",),
    "exercise": ("exercise",),
    "fact": ("fact",),
    "postulate": ("postulate",),
}
_ALIAS_TO_KIND = {a: k for k, al in KIND_ALIASES.items() for a in al}
_PROOF_WORDS = ("proof", "beweis", "démonstration", "demonstration")

_MARK = r"(?:\*\*|__|\*|_)?"
HEADER_RX = re.compile(
    r"^\s*" + _MARK + r"\s*(?P<kind>[A-Za-z]+)\s*"
    r"(?P<num>\d+(?:\.\d+)*[a-z]?)?\s*"
    r"(?:\((?P<name>[^)]*)\))?\s*"
    + _MARK + r"\s*(?P<punct>[.:—–-])?\s*"
    r"(?:\{#(?P<id>[^}]+)\})?\s*(?P<rest>.*)$",
    re.S,
)
PROOF_RX = re.compile(
    r"^\s*" + _MARK + r"\s*(?P<word>[A-Za-zé]+)"
    r"(?:\s+of\s+(?P<tkind>[A-Za-z]+)\s*(?P<tnum>\d+(?:\.\d+)*[a-z]?)?"
    r"(?:\s*\((?P<tname>[^)]*)\))?)?"
    r"[^.:\n]*?" + _MARK + r"\s*(?P<punct>[.:])\s*(?P<rest>.*)$",
    re.S,
)
HEADING_RX = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
HEADING_ID_RX = re.compile(r"\s*\{#([^}]+)\}\s*$")
FRONTMATTER_START_RX = re.compile(r"^---\s*$")
FM_TITLE_RX = re.compile(r"^\s*title:\s*(.+?)\s*$")
FM_PERMALINK_RX = re.compile(r"^\s*permalink:\s*(\S+)\s*$")
QED_RX = re.compile(r"(∎|□|■|\bQ\.?E\.?D\b\.?|\\qed\b|\\blacksquare\b)\s*$")

LINK_RX = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BOLD_RX = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)
QUOTE_RX = re.compile(r"[\"“]([^\"”\n]{2,60})[\"”]")
CALLED_RX = re.compile(
    r"\b(?:called|termed|known as)\s+(?:an?\s+|the\s+)?"
    r"([A-Za-z][A-Za-z\-]*(?:\s+[A-Za-z][A-Za-z\-]*){0,3}?)"
    r"(?=\s*(?:[,.;:)]|\bif\b|\bwhen\b|\bwhenever\b|\bsuch\b|\bthat\b"
    r"|\bwhich\b|\bwith\b|\bwhere\b|\bprovided\b|\bof\b|\bfor\b|\bon\b|$))",
    re.I,
)
TEXT_REF_RX = re.compile(
    r"\b(" + "|".join(sorted({a for al in KIND_ALIASES.values() for a in al},
                             key=len, reverse=True))
    + r")s?\.?\s+(\d+(?:\.\d+)*[a-z]?)\b",
    re.I,
)


def slugify(s):
    s = s.strip().lower().replace("_", "-")
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"[^\w\-]", "", s)          # \w is Unicode-aware: α, ö, … survive
    return s.strip("-")


def strip_markup(text):
    """Remove Markdown/LaTeX-ish markup and math, keep the running text."""
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.S)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = LINK_RX.sub(r"\1", text)
    text = re.sub(r"<[^>\n]+>", " ", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"\{#[^}]+\}", " ", text)
    text = text.replace("**", " ").replace("__", " ")
    text = re.sub(r"(?<![A-Za-z0-9])[*_]|[*_](?![A-Za-z0-9])", " ", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return text


def _kind_of(word):
    return _ALIAS_TO_KIND.get(word.lower())


def _match_header(line, require_marker=True):
    """Return (kind, num, name, id, body_start_text) or None."""
    m = HEADER_RX.match(line)
    if not m:
        return None
    kind = _kind_of(m.group("kind"))
    if kind is None:
        return None
    if require_marker and not (m.group("punct") or m.group("name")
                               or m.group("id")
                               or m.group(0).lstrip().startswith(("*", "_"))):
        # "Lemma 3 together with ..." in the middle of a wrapped paragraph
        # is prose; a header needs punctuation, a (name), an {#id} or bold.
        return None
    return kind, m.group("num"), m.group("name"), m.group("id"), m.group("rest")


def _match_proof(line):
    m = PROOF_RX.match(line)
    if not m or m.group("word").lower() not in _PROOF_WORDS:
        return None
    tkind = _kind_of(m.group("tkind")) if m.group("tkind") else None
    return tkind, m.group("tnum"), m.group("tname"), m.group("rest")


# ------------------------------------------------------------------
# Block scanner
# ------------------------------------------------------------------

class _Block:
    __slots__ = ("kind", "num", "name", "id", "title", "permalink",
                 "start", "end", "lines", "is_proof", "is_entry",
                 "is_heading", "proof_target", "proof_tkind", "proof_tnum",
                 "proof_tname")

    def __init__(self, kind, start):
        self.kind = kind
        self.num = self.name = self.id = self.title = self.permalink = None
        self.start = start
        self.end = start
        self.lines = []
        self.is_proof = False
        self.is_entry = False
        self.is_heading = False     # opened by a Markdown heading: runs to the next heading
        self.proof_target = None
        self.proof_tkind = self.proof_tnum = self.proof_tname = None


def _scan_blocks(text):
    """Split text into statement / proof / entry blocks."""
    lines = text.splitlines(keepends=True)
    offsets = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    offsets.append(pos)

    blocks = []
    headings = []          # (line_no, title, id, permalink) without keyword
    cur = None
    i = 0
    n = len(lines)

    def close(at_line):
        nonlocal cur
        if cur is not None:
            cur.end = offsets[at_line]
            blocks.append(cur)
            cur = None

    while i < n:
        raw = lines[i]
        line = raw.rstrip("\n")

        # YAML front matter (MathGloss-style glossary pages)
        if FRONTMATTER_START_RX.match(line):
            j = i + 1
            title = permalink = None
            while j < n and not FRONTMATTER_START_RX.match(lines[j].rstrip("\n")):
                tm = FM_TITLE_RX.match(lines[j])
                pm = FM_PERMALINK_RX.match(lines[j])
                if tm:
                    title = tm.group(1).strip().strip("\"'")
                if pm:
                    permalink = pm.group(1)
                j += 1
            if j < n and title:
                close(i)
                cur = _Block("definition", offsets[j + 1])
                cur.is_entry = True
                cur.title = title
                cur.permalink = permalink
                i = j + 1
                continue
            # not a front matter block: fall through

        hm = HEADING_RX.match(line)
        if hm:
            htext = hm.group(2)
            hid = None
            im = HEADING_ID_RX.search(htext)
            if im:
                hid = im.group(1)
                htext = htext[:im.start()]
            close(i)
            pm = _match_proof(htext) or _match_proof(htext.rstrip() + ".")
            hdr = None if pm else _match_header(htext, require_marker=False)
            if pm:
                # "## Proof" / "## Proof of Theorem 2.1"
                cur = _proof_block(pm, offsets[i])
                cur.is_heading = True
            elif hdr:
                kind, num, name, _id, rest = hdr
                cur = _Block(kind, offsets[i])
                cur.num, cur.name, cur.id = num, name, (hid or _id)
                cur.title = htext.strip()
                cur.is_heading = True
                if rest.strip():
                    cur.lines.append(rest)
            else:
                cur = _Block("definition", offsets[i])
                cur.is_entry = True
                cur.title = htext.strip()
                cur.id = hid
            i += 1
            continue

        pm = _match_proof(line)
        if pm:
            close(i)
            cur = _proof_block(pm, offsets[i])
            if QED_RX.search(line):
                close(i + 1)
            i += 1
            continue

        hdr = _match_header(line)
        if hdr:
            close(i)
            kind, num, name, _id, rest = hdr
            cur = _Block(kind, offsets[i])
            cur.num, cur.name, cur.id = num, name, _id
            cur.lines.append(rest)
            i += 1
            continue

        if cur is not None:
            if cur.is_proof:
                cur.lines.append(line)
                if QED_RX.search(line):
                    close(i + 1)
            elif cur.is_entry or cur.is_heading:
                # Heading-opened blocks run to the next heading or header,
                # so the usual "## Theorem 1", blank line, paragraph layout
                # keeps its body.
                cur.lines.append(line)
            else:
                if line.strip() == "":
                    close(i)
                else:
                    cur.lines.append(line)
        i += 1

    close(n)
    return blocks


def _proof_block(pm, start):
    tkind, tnum, tname, rest = pm
    b = _Block("proof", start)
    b.is_proof = True
    b.proof_tkind, b.proof_tnum, b.proof_tname = tkind, tnum, tname
    if tkind and tnum:
        b.proof_target = f"{tkind}:{tnum}"
    elif tkind and tname:
        b.proof_target = f"{tkind}:{slugify(tname)}"
    if rest.strip():
        b.lines.append(rest)
    return b


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

def parse_text_structure(text, headings_as_entries=None):
    """Parse Markdown (or keyword-only text) into KnowTeX nodes and proofs.

    headings_as_entries: True = every keyword-less heading is a definition
    entry (glossary mode); False = such headings are section titles only;
    None = glossary mode iff the text contains no keyword blocks.
    """
    blocks = _scan_blocks(text)

    has_keyword_blocks = any(not b.is_entry and not b.is_proof for b in blocks)
    if headings_as_entries is None:
        headings_as_entries = not has_keyword_blocks
    if not headings_as_entries:
        blocks = [b for b in blocks
                  if not (b.is_entry and b.title is not None
                          and b.permalink is None)]

    nodes = []
    node_by_index = {}
    label_to_node = {}
    proofs = []
    discovered_envs = set()
    used_labels = set()
    slug_to_label = {}
    number_to_label = {}

    # First pass: labels (so references can be resolved afterwards)
    prepared = []
    order = 0
    last_stmt_idx = None
    for b in blocks:
        body = "\n".join(b.lines)
        plain = strip_markup(body)
        if b.is_entry and b.title:
            # The title names the concept; keep it in the running text
            # so other definitions' terms can match it.
            plain = f"{b.title}. {plain}"
        if b.is_proof:
            prepared.append((b, order, body, plain, None, None, last_stmt_idx))
            order += 1
            continue

        kind = b.kind
        terms = _defined_terms(kind, b, body)
        label = None
        if b.id:
            label = b.id.strip()
        elif b.num:
            label = f"{kind}:{b.num}"
        elif b.name:
            label = f"{kind}:{slugify(b.name)}"
        elif b.is_entry and b.title:
            label = f"{kind}:{slugify(b.title)}"
        elif terms:
            label = f"{kind}:{slugify(terms[0])}"
        if not label or label in used_labels:
            base = label or f"{kind}:{order}"
            label = base if base not in used_labels else f"{base}:{order}"
        used_labels.add(label)

        if b.num:
            number_to_label[(kind, b.num)] = label
        for s in _slug_candidates(b, terms, label):
            slug_to_label.setdefault(s, label)

        prepared.append((b, order, body, plain, label, terms, None))
        last_stmt_idx = order
        order += 1

    # Second pass: build nodes with resolved references
    for b, idx, body, plain, label, terms, tgt_idx in prepared:
        refs = _resolve_refs(body, slug_to_label, number_to_label, label)
        if b.is_proof:
            target_label = b.proof_target
            if target_label and target_label not in used_labels:
                # The statement may carry a {#label}: look it up by number
                # ("Proof of Theorem 2.1") or by name ("Proof of Theorem (Lagrange)").
                if b.proof_tnum:
                    target_label = number_to_label.get(
                        (b.proof_tkind, b.proof_tnum), target_label)
                elif b.proof_tname:
                    target_label = slug_to_label.get(
                        slugify(b.proof_tname), target_label)
            proofs.append(ProofInfo(
                index=idx, target_label=target_label, snippet=body,
                pos=b.start, pos_end=b.end, target_node_idx=tgt_idx,
                text=plain, refs=tuple(refs),
            ))
            continue

        display = _display_name(b, label, terms)
        ni = NodeInfo(
            env=b.kind, label=label, index=idx, snippet=body,
            pos=b.start, pos_end=b.end, display_name=display,
            text=plain, defined_terms=tuple(terms), refs=tuple(refs),
        )
        nodes.append(ni)
        node_by_index[idx] = ni
        label_to_node[label] = ni
        discovered_envs.add(b.kind)

    # D3: explicit proof targets
    for i, p in enumerate(proofs):
        if p.target_label and p.target_label in label_to_node:
            proofs[i] = p._replace(
                target_node_idx=label_to_node[p.target_label].index)

    return nodes, node_by_index, label_to_node, proofs, discovered_envs


def _slug_candidates(b, terms, label):
    out = []
    if b.title:
        out.append(slugify(b.title))
    if b.permalink:
        out.append(slugify(b.permalink.rstrip("/").rsplit("/", 1)[-1]))
    if b.name:
        out.append(slugify(b.name))
    for t in terms[:1]:
        out.append(slugify(t))
    out.append(slugify(label.split(":", 1)[-1]))
    return [s for s in out if s]


def _defined_terms(kind, b, body):
    terms = []
    seen = set()

    def add(t):
        t = " ".join(strip_markup(t).split()).strip(" .,;:")
        if len(t) >= 2 and t.lower() not in seen:
            seen.add(t.lower())
            terms.append(t)

    is_defn_kind = bool(DEFN_ENV_RX.match(kind))
    if b.is_entry and b.title:
        # Glossary entry: the title is the defined term.  Bold words in
        # the body are usually the same term or a fragment of it
        # ("algebra" inside "algebra of subsets"), which over-matches,
        # so they are not used here.
        add(b.title)
        return terms
    if is_defn_kind and b.name:
        add(b.name)
    for m in BOLD_RX.finditer(body):
        add(m.group(1) or m.group(2) or "")
    if is_defn_kind:
        for m in QUOTE_RX.finditer(body):
            add(m.group(1))
        for m in CALLED_RX.finditer(body):
            add(m.group(1))
    return terms


def _resolve_refs(body, slug_to_label, number_to_label, own_label):
    refs = []
    for m in LINK_RX.finditer(body):
        target = m.group(2)
        if target.startswith("#"):
            cand = target[1:]
            lbl = cand if cand in slug_to_label.values() else slug_to_label.get(slugify(cand))
        else:
            seg = target.rstrip("/").rsplit("/", 1)[-1]
            seg = seg.split("?", 1)[0].split("#", 1)[0]
            seg = re.sub(r"\.(md|html?)$", "", seg)
            lbl = slug_to_label.get(slugify(seg))
        if lbl and lbl != own_label and lbl not in refs:
            refs.append(lbl)
    for m in TEXT_REF_RX.finditer(body):
        kind = _kind_of(m.group(1))
        lbl = number_to_label.get((kind, m.group(2)))
        if lbl and lbl != own_label and lbl not in refs:
            refs.append(lbl)
    return refs


def _display_name(b, label, terms):
    if b.name:
        return b.name.strip()
    if b.is_entry and b.title:
        return b.title.strip()
    if b.num:
        return f"{b.kind.capitalize()} {b.num}"
    if ":" in label:
        return label.split(":", 1)[1].replace("-", " ")
    return label
