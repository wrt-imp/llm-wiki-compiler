"""Nodes, edges and the graph they form.

The graph is a plain in-memory structure built from a KnowledgeBase: nodes are
entities and concepts (identified by their ``object_id``), edges are relations
and, when the IR gives a complete triple, facts. Edge endpoints stay the names
as written in the knowledge base, while ``metadata["source_id"]`` /
``["target_id"]`` pin an endpoint to one node when it could be resolved
uniquely.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from ..knowledge import Fact, Relation, SourceRef
from ..merge.normalize import alias_keys, match_key

KIND_ENTITY = "entity"
KIND_CONCEPT = "concept"
KIND_RELATION = "relation"
KIND_FACT = "fact"

_KIND_ORDER = {KIND_ENTITY: 0, KIND_CONCEPT: 1}

#: Node metadata keys that hold typed :class:`SourceRef` objects.
SOURCES_KEY = "sources"


@dataclass(frozen=True)
class Node:
    """One knowledge object: an entity or a concept."""

    id: str
    kind: str
    title: str
    aliases: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata: {"description": str, "sources": [SourceRef, ...],
    #            "type": str (entities only)}

    def name_keys(self) -> List[str]:
        """Normalized names this node answers to (title plus aliases)."""

        return alias_keys(self.title, self.aliases)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "aliases": list(self.aliases),
            "metadata": _metadata_to_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Node":
        return cls(
            id=data["id"],
            kind=data["kind"],
            title=data["title"],
            aliases=tuple(data.get("aliases", [])),
            metadata=_metadata_from_dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class Edge:
    """A directed link between two knowledge objects.

    ``source`` and ``target`` are the names as written in the knowledge base;
    ``metadata`` carries the resolved node ids (when unique), the description,
    the evidence and - for fact edges - the original statement.
    """

    source: str
    target: str
    type: str
    kind: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata: {"source_id"/"target_id": str|None, "description": str,
    #            "statements": [str], "kinds": [str], "sources": [SourceRef]}

    @property
    def source_id(self) -> Optional[str]:
        return self.metadata.get("source_id")

    @property
    def target_id(self) -> Optional[str]:
        return self.metadata.get("target_id")

    @property
    def is_self_loop(self) -> bool:
        return match_key(self.source) == match_key(self.target)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "kind": self.kind,
            "metadata": _metadata_to_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Edge":
        return cls(
            source=data["source"],
            target=data["target"],
            type=data.get("type", ""),
            kind=data.get("kind", ""),
            metadata=_metadata_from_dict(data.get("metadata", {})),
        )


@dataclass
class Graph:
    """The knowledge graph of one KnowledgeBase."""

    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    documents: List[Dict[str, Any]] = field(default_factory=list)
    unlinked_relations: List[Relation] = field(default_factory=list)
    unlinked_facts: List[Fact] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_node(self, node_id: str) -> Optional[Node]:
        """Return the node with ``node_id``, or ``None`` when unknown."""

        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_nodes(self) -> List[Node]:
        """Every node, in the graph's stable order."""

        return list(self.nodes)

    def get_edges(self) -> List[Edge]:
        """Every edge, in the graph's stable order."""

        return list(self.edges)

    def outgoing(self, node_id: str) -> List[Edge]:
        """Edges leaving ``node_id`` (self loops included)."""

        node = self.get_node(node_id)
        if node is None:
            return []
        return [edge for edge in self.edges if _edge_touches(edge, node, "source")]

    def incoming(self, node_id: str) -> List[Edge]:
        """Edges arriving at ``node_id`` (self loops included)."""

        node = self.get_node(node_id)
        if node is None:
            return []
        return [edge for edge in self.edges if _edge_touches(edge, node, "target")]

    def neighbors(self, node_id: str) -> List[Node]:
        """Nodes connected to ``node_id`` in either direction, de-duplicated."""

        node = self.get_node(node_id)
        if node is None:
            return []

        found: Dict[str, Node] = {}
        for edge in self.outgoing(node_id):
            for other in self._endpoint_nodes(edge.target, edge.target_id):
                found.setdefault(other.id, other)
        for edge in self.incoming(node_id):
            for other in self._endpoint_nodes(edge.source, edge.source_id):
                found.setdefault(other.id, other)
        return sorted(found.values(), key=node_sort_key)

    def _endpoint_nodes(self, name: str, pinned_id: Optional[str]) -> List[Node]:
        """Nodes an edge endpoint refers to: the pinned id, else the name."""

        if pinned_id:
            node = self.get_node(pinned_id)
            return [node] if node is not None else []
        key = match_key(name)
        return [node for node in self.nodes if key in set(node.name_keys())]

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "documents": [dict(document) for document in self.documents],
            "unlinked_relations": [
                {
                    "source": relation.source,
                    "target": relation.target,
                    "type": relation.type,
                    "description": relation.description,
                    "sources": [source.to_dict() for source in relation.sources],
                }
                for relation in self.unlinked_relations
            ],
            "unlinked_facts": [
                {
                    "statement": fact.statement,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "object": fact.object,
                    "sources": [source.to_dict() for source in fact.sources],
                }
                for fact in self.unlinked_facts
            ],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Graph":
        return cls(
            nodes=[Node.from_dict(item) for item in data.get("nodes", [])],
            edges=[Edge.from_dict(item) for item in data.get("edges", [])],
            documents=[dict(item) for item in data.get("documents", [])],
            unlinked_relations=[
                Relation(
                    source=item["source"],
                    target=item["target"],
                    type=item.get("type", ""),
                    description=item.get("description", ""),
                    sources=[
                        SourceRef.from_dict(source)
                        for source in item.get("sources", [])
                    ],
                )
                for item in data.get("unlinked_relations", [])
            ],
            unlinked_facts=[
                Fact(
                    statement=item["statement"],
                    subject=item.get("subject", ""),
                    predicate=item.get("predicate", ""),
                    object=item.get("object", ""),
                    sources=[
                        SourceRef.from_dict(source)
                        for source in item.get("sources", [])
                    ],
                )
                for item in data.get("unlinked_facts", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )


def node_sort_key(node: Node) -> Tuple[int, str, str]:
    """Stable node order: entity before concept, then name, then id."""

    return (_KIND_ORDER.get(node.kind, 9), match_key(node.title), node.id)


def edge_sort_key(edge: Edge) -> Tuple[str, str, str, str]:
    """Stable edge order: source, type, target, kind."""

    return (
        match_key(edge.source),
        match_key(edge.type),
        match_key(edge.target),
        edge.kind,
    )


def edge_identity(edge: Edge) -> Tuple[str, str, str]:
    """Edges are the same when source, type and target match."""

    return (match_key(edge.source), match_key(edge.type), match_key(edge.target))


def merge_edges(first: Edge, second: Edge) -> Edge:
    """Merge two edges with the same identity, keeping every source."""

    metadata = dict(first.metadata)
    metadata["sources"] = merge_source_refs(
        first.metadata.get(SOURCES_KEY, []), second.metadata.get(SOURCES_KEY, [])
    )
    kinds = list(metadata.get("kinds", []))
    for kind in second.metadata.get("kinds", []):
        if kind not in kinds:
            kinds.append(kind)
    metadata["kinds"] = sorted(kinds)
    statements = list(metadata.get("statements", []))
    for statement in second.metadata.get("statements", []):
        if statement not in statements:
            statements.append(statement)
    metadata["statements"] = statements
    for key in ("source_id", "target_id"):
        if metadata.get(key) is None:
            metadata[key] = second.metadata.get(key)
    if not metadata.get("description"):
        metadata["description"] = second.metadata.get("description", "")
    return replace(first, metadata=metadata)


def merge_source_refs(*groups: Any) -> List[SourceRef]:
    """Union of source references, de-duplicated, order preserved."""

    result: List[SourceRef] = []
    seen = set()
    for group in groups:
        for source in group:
            key = (
                source.document_id,
                source.section_id,
                source.page_number,
                source.quote,
            )
            if key not in seen:
                seen.add(key)
                result.append(source)
    return result


def _edge_touches(edge: Edge, node: Node, side: str) -> bool:
    pinned = edge.metadata.get(f"{side}_id")
    if pinned:
        return pinned == node.id
    return match_key(getattr(edge, side)) in set(node.name_keys())


def _metadata_to_dict(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Copy metadata, turning SourceRef values into plain dictionaries."""

    result: Dict[str, Any] = {}
    for key, value in metadata.items():
        if key == SOURCES_KEY:
            result[key] = [
                source.to_dict() if isinstance(source, SourceRef) else source
                for source in value
            ]
        elif isinstance(value, tuple):
            result[key] = list(value)
        else:
            result[key] = value
    return result


def _metadata_from_dict(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Copy metadata, restoring the ``sources`` entries to SourceRef objects."""

    result: Dict[str, Any] = dict(metadata)
    if SOURCES_KEY in result:
        result[SOURCES_KEY] = [
            source if isinstance(source, SourceRef) else SourceRef.from_dict(source)
            for source in result[SOURCES_KEY]
        ]
    return result
