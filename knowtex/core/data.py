"""Core data structures: nodes, proofs, and dependency edges."""

from dataclasses import dataclass
from typing import Literal, NamedTuple

EdgeType = Literal["deterministic", "heuristic", "manual"]
Location = Literal["proof", "statement", "inferred"]
RuleName = Literal["D1", "D2", "D3", "D4", "H2", "H3", "H4", "manual"]


class NodeInfo(NamedTuple):
    """A single theorem-like statement in the LaTeX document.

    Proof is NOT a separate node -- it belongs to its parent statement.
    """
    env: str            # Environment name (theorem, lemma, definition, ...)
    label: str          # Unique identifier from \\label{X} or auto-generated
    index: int          # Sequential document-order index
    snippet: str        # Full LaTeX source of the environment
    pos: int            # Start character position in expanded text
    pos_end: int        # End character position in expanded text
    display_name: str   # Short human-readable name


class ProofInfo(NamedTuple):
    """A proof environment and its association to a parent statement.

    target_node_idx is initially set by H1 (nearest preceding statement)
    and may be overridden by D3 (explicit proof target from header) or
    \\proves{} during parsing.
    """
    index: int                    # Sequential document-order index
    target_label: str | None      # Explicit target from \\proves{} or proof header
    snippet: str                  # Full LaTeX source of the proof environment
    pos: int                      # Start character position in expanded text
    pos_end: int                  # End character position in expanded text
    target_node_idx: int | None   # Index of the parent statement node


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """A dependency relationship between two nodes.

    Edge direction convention:
        source -> target  means  "target depends on source"

    Equivalently: source is a prerequisite of target.
    In the rendered graph the arrow points from source to target,
    indicating that knowledge flows from source into target.

    Used by both manual (\\uses{}/\\proves{}) and inferred modes.
    """
    source: str            # Prerequisite node label
    target: str            # Dependent node label
    edge_type: EdgeType    # "deterministic" or "heuristic" or "manual"
    location: Location     # "proof", "statement", or "inferred"
    rule: RuleName         # "D1", "D2", "D3", "D4", "H2", "H3", "H4", "manual"

    def key(self) -> tuple:
        return (self.source, self.target)
