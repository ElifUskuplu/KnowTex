"""Extract dependency edges from explicit \\uses{} commands.

This is the manual mode: the author has already annotated their LaTeX
with \\uses{label1, label2}.  (\\proves{} is read by the parser, which
uses it to retarget a proof.)
"""

from knowtex.core.constants import USES_RX, split_labels
from knowtex.core.data import DependencyEdge, proof_targets


def extract_manual_edges(nodes, node_by_index, label_to_node, proofs):
    """Read explicit \\uses{} from node/proof snippets.

    Returns: list[DependencyEdge] with rule='manual'.
    Edge types:
      - \\uses{} in a statement body -> edge_type="manual", location="statement"
      - \\uses{} in a proof body -> edge_type="manual", location="proof"
    """
    edges = []
    seen = set()

    def add_edge(source, target, location):
        """Record that *target* depends on *source* (source -> target)."""
        key = (source, target)
        if key not in seen and source != target:
            seen.add(key)
            edges.append(
                DependencyEdge(source, target, "manual", location, "manual")
            )

    all_labels = set(label_to_node.keys())

    # Statement-level \\uses{}
    for ni in nodes:
        for um in USES_RX.finditer(ni.snippet):
            for lbl in split_labels(um.group(1)):
                if lbl in all_labels and lbl != ni.label:
                    add_edge(lbl, ni.label, "statement")

    # Proof-level \\uses{}: to every statement the proof proves
    for p in proofs:
        for tgt_idx in proof_targets(p):
            tgt_node = node_by_index.get(tgt_idx)
            if not tgt_node:
                continue
            parent_label = tgt_node.label
            for um in USES_RX.finditer(p.snippet):
                for lbl in split_labels(um.group(1)):
                    if lbl in all_labels and lbl != parent_label:
                        add_edge(lbl, parent_label, "proof")

    return edges
