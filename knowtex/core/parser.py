"""LaTeX structure parser (pylatexenc AST-based).

Extracts the structural skeleton: theorem-like nodes and proof environments.
Edge extraction is handled separately by deps/manual.py and deps/infer.py.
"""

import logging
import re

from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode

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


def _compute_display_name(env_name, lbl, label, snippet, index):
    """Compute a short human-readable display name for a node.

    Args:
        env_name: environment name
        lbl: explicit \\label{} value (None if not found)
        label: final resolved label (from hierarchy)
        snippet: full LaTeX source
        index: sequential document-order index
    """
    if ":" in label:
        name = label.split(":", 1)[1]
        return name.replace("-", " ")
    return f"{env_name.capitalize()} {index}"


def parse_latex_structure(tex):
    """Parse LaTeX using pylatexenc AST walker.

    Returns: (nodes, node_by_index, label_to_node, proofs, discovered_envs)
    """
    lw = LatexWalker(tex)
    nodelist, _, _ = lw.get_latex_nodes()

    nodes = []
    node_by_index = {}
    label_to_node = {}
    proofs = []
    discovered_envs = set()

    order_counter = 0
    last_stmt_idx = None
    used_labels = set()

    def walk(n):
        nonlocal order_counter, last_stmt_idx

        if isinstance(n, LatexEnvironmentNode):
            env = n.environmentname

            if is_theorem_like(env):
                discovered_envs.add(env)
                my_index = order_counter
                order_counter += 1
                last_stmt_idx = my_index

                try:
                    end = getattr(n, 'pos_end', None)
                    if end is None:
                        end = n.pos + n.len
                    snippet = tex[n.pos:end]
                    pos = n.pos
                    pos_end = end
                except Exception:
                    logger.debug("pos-based snippet failed for %s, "
                                 "using latex_verbatim()", env,
                                 exc_info=True)
                    snippet = n.latex_verbatim()
                    pos = 0
                    pos_end = len(snippet)

                # --- Label hierarchy ---
                # Step 1: \label{} (skip labels inside inner math envs)
                lbl = None
                for lm in LABEL_RX.finditer(snippet):
                    candidate = lm.group(1)
                    preceding = snippet[:lm.start()]
                    if not _is_inside_inner_env(preceding):
                        lbl = candidate
                        break

                if lbl:
                    label = lbl
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
                        candidate_label = f"{env}:{candidate}"
                        if candidate_label not in used_labels:
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
                                parts = norm.split("!")
                                norm = " ".join(reversed(parts))
                            derived = norm.replace(" ", "-")
                            break

                    # Produce label or fallback
                    if derived:
                        candidate_label = f"{env}:{derived}"
                        if candidate_label in used_labels:
                            candidate_label = f"{env}:{derived}:{my_index}"
                        label = candidate_label
                    else:
                        # Step 4: Fallback
                        label = f"{env}:{my_index}"

                    used_labels.add(label)

                display_name = _compute_display_name(
                    env, lbl, label, snippet, my_index
                )

                ni = NodeInfo(
                    env=env, label=label,
                    index=my_index, snippet=snippet,
                    pos=pos, pos_end=pos_end,
                    display_name=display_name,
                )
                nodes.append(ni)
                node_by_index[my_index] = ni
                label_to_node[label] = ni
                if lbl and lbl != label:
                    label_to_node[lbl] = ni

            elif PROOF_ALIAS_RX.fullmatch(env or ""):
                my_index = order_counter
                order_counter += 1

                try:
                    end = getattr(n, 'pos_end', None)
                    if end is None:
                        end = n.pos + n.len
                    snippet = tex[n.pos:end]
                    pos = n.pos
                    pos_end = end
                except Exception:
                    logger.debug("pos-based snippet failed for proof env, "
                                 "using latex_verbatim()", exc_info=True)
                    snippet = n.latex_verbatim()
                    pos = 0
                    pos_end = len(snippet)

                # D3: explicit proof target from header
                pm = PROOF_OF_REF_RX.search(snippet)
                target_label = pm.group(1).strip() if pm else None

                if not target_label:
                    prv = PROVES_RX.search(snippet)
                    if prv:
                        target_label = prv.group(1).strip()

                proofs.append(ProofInfo(
                    index=my_index,
                    target_label=target_label,
                    snippet=snippet,
                    pos=pos,
                    pos_end=pos_end,
                    target_node_idx=last_stmt_idx,  # H1 default
                ))

            # Recurse into children
            for ch in (n.nodelist or []):
                walk(ch)
        else:
            if hasattr(n, "nodelist") and n.nodelist:
                for ch in n.nodelist:
                    walk(ch)

    for root in nodelist:
        walk(root)

    # Resolve explicit proof targets (D3)
    for i, p in enumerate(proofs):
        if p.target_label and p.target_label in label_to_node:
            proofs[i] = p._replace(
                target_node_idx=label_to_node[p.target_label].index
            )

    return nodes, node_by_index, label_to_node, proofs, discovered_envs
