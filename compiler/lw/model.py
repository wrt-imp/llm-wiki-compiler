"""The parsed model of a ``.lw`` (Mermaid) graph source.

These types belong to the parsing stage only: they describe *how the source
file is written*. The adapter turns them into the project's long lived
``Graph`` (nodes and edges), which describes *what the graph is*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MermaidNode:
    """One node of the source file: an id plus its display label."""

    id: str
    label: str = ""
    line: int = 0
    column: int = 0

    @property
    def display_name(self) -> str:
        return self.label or self.id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True)
class MermaidEdge:
    """One directed link of the source file."""

    source: str
    target: str
    label: str = ""
    bidirectional: bool = False
    line: int = 0
    column: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "bidirectional": self.bidirectional,
            "line": self.line,
            "column": self.column,
        }


@dataclass
class MermaidDocument:
    """A parsed Mermaid graph: direction, nodes and edges."""

    direction: str = ""
    nodes: List[MermaidNode] = field(default_factory=list)
    edges: List[MermaidEdge] = field(default_factory=list)
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def node(self, node_id: str) -> Optional[MermaidNode]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MermaidDocument":
        return cls(
            direction=data.get("direction", ""),
            nodes=[MermaidNode(**item) for item in data.get("nodes", [])],
            edges=[MermaidEdge(**item) for item in data.get("edges", [])],
            source=data.get("source", ""),
            metadata=dict(data.get("metadata", {})),
        )
