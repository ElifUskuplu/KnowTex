"""LaTeX structure parser.

Extracts the structural skeleton: theorem-like nodes and proof environments.
Edge extraction is handled separately by deps/manual.py and deps/infer.py.

Two engines find the ``\\begin{env} ... \\end{env}`` pairs:

* ``fast`` (default): a single regex pass over the text with a stack of
  open environments.  Comments, ``\\verb`` and verbatim-like bodies are
  blanked out first (same length, so every position still refers to the
  original text).  About a hundred times faster than the AST walk.
* ``ast``: the pylatexenc AST walk this parser was built on, kept for
  comparison (``KNOWTEX_PARSER=ast``; ``pip install pylatexenc``).

Both engines hand the same list of environments, in document order, to
the same node and proof extraction, so they produce identical results on
well-formed documents (see ``TestFastParserMatchesAst``).
"""

import logging
import os
import re

logger = logging.getLogger("knowtex")

from knowtex.core.constants import (
    PROOF_ALIAS_RX, SKIP_ENVS, LABEL_RX, PROVES_RX,
    INDEX_RX, PROOF_OF_REF_RX, EMPH_RX, INNER_LABEL_ENVS,
)
from knowtex.core.data import NodeInfo, ProofInfo
from knowtex.core.utils import normalize_index_term


def is_theorem_like(env_name):
    """Return True if this environment is a theorem-like statement
    (not a proof, not a well-known structural/math environment)."""
    if not env_name:
        return False
    if PROOF_ALIAS_RX.fullmatch(env_name):
        return False
    if env_name.lower() in SKIP_ENVS:
        return False
    return True


def _is_proof(env_name):
    return bool(PROOF_ALIAS_RX.fullmatch(env_name or ""))


def _is_inside_inner_env(preceding_text):
    """Check if position is inside an inner math environment."""
    depth = {}  # env_name -> open count
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", preceding_text):
        action, env_name = m.group(1), m.group(2)
        if env_name in INNER_LABEL_ENVS:
            if action == "begin":
                depth[env_name] = depth.get(env_name, 0) + 1
            else:
                depth[env_name] = max(0, depth.get(env_name, 0) - 1)
    return any(v > 0 for v in depth.values())


def _compute_display_name(env_name, label, index):
    """Short human-readable name: the part of the label after the colon,
    else "<Env> <index>"."""
    if ":" in label:
        name = label.split(":", 1)[1]
        return name.replace("-", " ")
    return f"{env_name.capitalize()} {index}"


# ---------------------------------------------------------------------------
# Environment discovery
# ---------------------------------------------------------------------------
# Both engines return [(env, pos, pos_end, depth)] for every theorem-like
# or proof environment, in order of their \begin; *depth* counts the
# theorem-like environments enclosing it.

# A "%" preceded by an even number of backslashes starts a comment (so
# "\%" is a percent sign but "\\%" is a line break followed by a comment).
_COMMENT_RX = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*")
_VERB_RX = re.compile(r"\\verb\*?(?P<d>[^a-zA-Z\s])(?:(?!(?P=d)).)*(?P=d)")
_VERBATIM_ENVS = ("verbatim", "verbatim*", "lstlisting", "lstlisting*",
                  "minted", "comment", "Verbatim", "alltt")
_VERBATIM_RX = re.compile(
    r"\\begin\s*\{(" + "|".join(re.escape(e) for e in _VERBATIM_ENVS) + r")\}"
    r".*?\\end\s*\{\1\}", re.S)
# \begin{env} / \end{env}; group 1 holds the run of "\\" pairs before the
# command (an even number of backslashes), so "\\begin{x}" is a line break
# followed by the word "begin".
_ENV_TOKEN_RX = re.compile(r"(?<!\\)((?:\\\\)*)\\(begin|end)\s*\{([^{}]*)\}")


def _blank(m, keep=0):
    s = m.group(0)
    return s[:keep] + " " * (len(s) - keep)


def _masked(tex):
    """The text with comments, \\verb arguments and verbatim-like
    environments replaced by spaces of the same length."""
    tex = _VERBATIM_RX.sub(_blank, tex)
    tex = _COMMENT_RX.sub(lambda m: _blank(m, len(m.group(1))), tex)
    tex = _VERB_RX.sub(_blank, tex)
    return tex


def _environments_fast(tex):
    found = []           # (begin_order, env, pos, pos_end, depth)
    stack = []           # [env, pos, depth, order]  for every open environment
    tdepth = 0           # theorem-like environments currently open
    order = 0
    for m in _ENV_TOKEN_RX.finditer(_masked(tex)):
        env = m.group(3).strip()
        if m.group(2) == "begin":
            stack.append([env, m.start() + len(m.group(1)), tdepth, order])
            order += 1
            if is_theorem_like(env):
                tdepth += 1
            continue
        # \end{env}: close the innermost open environment of that name
        # (anything left open inside it ends here too)
        k = len(stack) - 1
        while k >= 0 and stack[k][0] != env:
            k -= 1
        if k < 0:
            continue
        while len(stack) > k:
            e, pos, depth, o = stack.pop()
            if is_theorem_like(e):
                tdepth -= 1
            if is_theorem_like(e) or _is_proof(e):
                found.append((o, e, pos, m.end() if len(stack) == k else m.start(), depth))
    for e, pos, depth, o in stack:               # never closed: run to the end
        if is_theorem_like(e) or _is_proof(e):
            found.append((o, e, pos, len(tex), depth))
    found.sort()
    return [(e, pos, end, depth) for _, e, pos, end, depth in found]


def _environments_ast(tex):
    from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode
    lw = LatexWalker(tex)
    nodelist, _, _ = lw.get_latex_nodes()
    found = []

    def walk(n, depth=0):
        if isinstance(n, LatexEnvironmentNode):
            env = n.environmentname
            if is_theorem_like(env) or _is_proof(env):
                try:
                    end = getattr(n, "pos_end", None)
                    if end is None:
                        end = n.pos + n.len
                    found.append((env, n.pos, end, depth))
                except Exception:
                    logger.debug("pos-based snippet failed for %s", env, exc_info=True)
                    found.append((env, n.pos, n.pos + len(n.latex_verbatim()), depth))
            inner = depth + 1 if is_theorem_like(env) else depth
            for ch in (n.nodelist or []):
                walk(ch, inner)
        elif hasattr(n, "nodelist") and n.nodelist:
            for ch in n.nodelist:
                walk(ch, depth)

    for root in nodelist:
        walk(root)
    return found


ENGINES = {"fast": _environments_fast, "ast": _environments_ast}


def parse_latex_structure(tex, engine=None):
    """Parse LaTeX into theorem-like nodes and proofs.

    *engine* is ``"fast"`` (default) or ``"ast"``; the environment variable
    ``KNOWTEX_PARSER`` sets the default.

    Returns: (nodes, node_by_index, label_to_node, proofs, discovered_envs)
    """
    engine = engine or os.environ.get("KNOWTEX_PARSER", "fast")
    envs_found = ENGINES[engine](tex)

    nodes = []
    node_by_index = {}
    label_to_node = {}
    proofs = []
    discovered_envs = set()
    used_labels = set()
    last_stmt_idx = None

    for my_index, (env, pos, pos_end, depth) in enumerate(envs_found):
        snippet = tex[pos:pos_end]
        if _is_proof(env):
            # D3: explicit proof target from header
            pm = PROOF_OF_REF_RX.search(snippet)
            target_label = pm.group(1).strip() if pm else None
            if not target_label:
                prv = PROVES_RX.search(snippet)
                if prv:
                    target_label = prv.group(1).strip()
            proofs.append(ProofInfo(
                index=my_index, target_label=target_label, snippet=snippet,
                pos=pos, pos_end=pos_end,
                target_node_idx=last_stmt_idx,  # H1 default
            ))
            continue

        discovered_envs.add(env)
        if depth == 0:
            # A statement nested inside another statement must not become
            # the H1 target of the proof that follows the outer one.
            last_stmt_idx = my_index

        # --- Label hierarchy ---
        # Step 1: \label{} (skip labels inside inner math envs)
        lbl = None
        for lm in LABEL_RX.finditer(snippet):
            if not _is_inside_inner_env(snippet[:lm.start()]):
                lbl = lm.group(1)
                break

        if lbl:
            label = lbl
            if label in used_labels:
                label = f"{lbl}:{my_index}"
                logger.warning("duplicate \\label{%s}; node %d renamed %s",
                               lbl, my_index, label)
        else:
            derived = None
            # Step 2: \demph / \emph / \textit / \textbf
            for emph_m in EMPH_RX.finditer(snippet):
                raw = emph_m.group(1).strip()
                if raw.startswith("\\") or raw.startswith("$"):
                    continue
                cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\{[^}]*\})?", " ", raw)
                cleaned = cleaned.replace("{", " ").replace("}", " ")
                cleaned = " ".join(cleaned.split()).strip().lower()
                if len(cleaned) < 2:
                    continue
                candidate = cleaned.replace(" ", "-")
                if f"{env}:{candidate}" not in used_labels:
                    derived = candidate
                    break
            # Step 3: \index{}
            if derived is None:
                for idx_m in INDEX_RX.finditer(snippet):
                    raw_idx = idx_m.group(1)
                    if "|see" in raw_idx.lower():
                        continue
                    norm = normalize_index_term(raw_idx)
                    if not norm:
                        continue
                    if "!" in norm:
                        norm = " ".join(reversed(norm.split("!")))
                    derived = norm.replace(" ", "-")
                    break
            if derived:
                label = f"{env}:{derived}"
                if label in used_labels:
                    label = f"{env}:{derived}:{my_index}"
            else:
                label = f"{env}:{my_index}"            # Step 4: fallback
        used_labels.add(label)

        ni = NodeInfo(
            env=env, label=label, index=my_index, snippet=snippet,
            pos=pos, pos_end=pos_end,
            display_name=_compute_display_name(env, label, my_index),
        )
        nodes.append(ni)
        node_by_index[my_index] = ni
        label_to_node[label] = ni

    # Resolve explicit proof targets (D3)
    for i, p in enumerate(proofs):
        if p.target_label and p.target_label in label_to_node:
            proofs[i] = p._replace(target_node_idx=label_to_node[p.target_label].index)

    return nodes, node_by_index, label_to_node, proofs, discovered_envs
