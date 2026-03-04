"""Extract dependency edges from explicit \\uses{} and \\proves{} commands.

This is the KnowTeX mode: the author has already annotated their LaTeX
with \\uses{label1, label2} commands.
"""

from knowtex.core.constants import USES_RX
from knowtex.core.data import DependencyEdge


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
            labels = [x.strip() for x in um.group(1).split(",") if x.strip()]
            for lbl in labels:
                if lbl in all_labels and lbl != ni.label:
                    add_edge(lbl, ni.label, "statement")

    # Proof-level \\uses{}
    for p in proofs:
        tgt_idx = p.target_node_idx
        if tgt_idx is None:
            continue
        tgt_node = node_by_index.get(tgt_idx)
        if not tgt_node:
            continue
        parent_label = tgt_node.label

        snippet = p.snippet
        for um in USES_RX.finditer(snippet):
            labels = [x.strip() for x in um.group(1).split(",") if x.strip()]
            for lbl in labels:
                if lbl in all_labels and lbl != parent_label:
                    add_edge(lbl, parent_label, "proof")

    return edges
