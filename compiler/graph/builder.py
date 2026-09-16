"""Build a Graph from a KnowledgeBase.

Rules:

1. Entity -> Node, Concept -> Node (de-duplicated by ``object_id``)
2. Relation -> Edge, but only when both endpoints exist
3. Fact -> Edge only when subject, predicate and object are all present *and*
   both endpoints exist; otherwise the fact stays unlinked (no invented edges)
4. edges keep the endpoint names as written; resolved node ids go to metadata
5. no dangling edges: an endpoint that matches no node keeps the relation
   unlinked and is reported as a warning
6. duplicated nodes and edges are merged, and sources are always unioned

The KnowledgeBase is read only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from ..knowledge import ENTITY_TYPE_OTHER, Fact, KnowledgeBase, Relation
from ..merge.normalize import match_key
from .model import (
    KIND_CONCEPT,
    KIND_ENTITY,
    KIND_FACT,
    KIND_RELATION,
    SOURCES_KEY,
    Edge,
    Graph,
    Node,
    edge_identity,
    edge_sort_key,
    merge_edges,
    merge_source_refs,
    node_sort_key,
)

GRAPH_BUILDER_VERSION = "graph-builder-v1"


def build_graph(knowledge_base: Any) -> Graph:
    """Turn one KnowledgeBase into a :class:`Graph`.

    Raises:
        TypeError: when the input is not a KnowledgeBase.
    """

    if not isinstance(knowledge_base, KnowledgeBase):
        raise TypeError(
            "build_graph expects a KnowledgeBase, got "
            f"{type(knowledge_base).__name__}"
        )

    warnings: List[str] = []
    ambiguous_names: set = set()

    nodes_by_id: Dict[str, Node] = {}
    for entity in knowledge_base.entities:
        _add_node(nodes_by_id, KIND_ENTITY, entity)
    for concept in knowledge_base.concepts:
        _add_node(nodes_by_id, KIND_CONCEPT, concept)
    nodes = sorted(nodes_by_id.values(), key=node_sort_key)
    index = _NameIndex(nodes)

    edges: Dict[Tuple[str, str, str], Edge] = {}
    unlinked_relations: List[Relation] = []
    for relation in knowledge_base.relations:
        source = index.resolve(relation.source, relation.source_id)
        target = index.resolve(relation.target, relation.target_id)
        _note_ambiguity(source, ambiguous_names)
        _note_ambiguity(target, ambiguous_names)
        if not (source.found and target.found):
            unlinked_relations.append(relation)
            warnings.append(_unlinked_message("relation", relation.source, source,
                                              relation.target, target))
            continue
        _add_edge(
            edges,
            Edge(
                source=relation.source,
                target=relation.target,
                type=relation.type,
                kind=KIND_RELATION,
                metadata={
                    "source_id": source.node_id,
                    "target_id": target.node_id,
                    "description": relation.description,
                    "statements": [],
                    "kinds": [KIND_RELATION],
                    SOURCES_KEY: list(relation.sources),
                    "ambiguous_source": source.ambiguous,
                    "ambiguous_target": target.ambiguous,
                },
            ),
        )

    unlinked_facts: List[Fact] = []
    for fact in knowledge_base.facts:
        if not (fact.subject and fact.predicate and fact.object):
            unlinked_facts.append(fact)
            warnings.append(
                f"fact {fact.statement!r} has no complete "
                "subject/predicate/object; kept unlinked"
            )
            continue
        source = index.resolve(fact.subject, None)
        target = index.resolve(fact.object, None)
        _note_ambiguity(source, ambiguous_names)
        _note_ambiguity(target, ambiguous_names)
        if not (source.found and target.found):
            unlinked_facts.append(fact)
            warnings.append(
                _unlinked_message(
                    "fact", fact.subject, source, fact.object, target
                )
            )
            continue
        _add_edge(
            edges,
            Edge(
                source=fact.subject,
                target=fact.object,
                type=fact.predicate,
                kind=KIND_FACT,
                metadata={
                    "source_id": source.node_id,
                    "target_id": target.node_id,
                    "description": "",
                    "statements": [fact.statement],
                    "kinds": [KIND_FACT],
                    SOURCES_KEY: list(fact.sources),
                    "ambiguous_source": source.ambiguous,
                    "ambiguous_target": target.ambiguous,
                },
            ),
        )

    edge_list = sorted(edges.values(), key=edge_sort_key)
    documents = [dict(document) for document in knowledge_base.documents]
    metadata: Dict[str, Any] = {
        "builder_version": GRAPH_BUILDER_VERSION,
        "nodes": len(nodes),
        "edges": len(edge_list),
        "relations": len(knowledge_base.relations),
        "facts": len(knowledge_base.facts),
        "self_loops": sum(1 for edge in edge_list if edge.is_self_loop),
        "unlinked_relations": len(unlinked_relations),
        "unlinked_facts": len(unlinked_facts),
        "ambiguous_names": sorted(ambiguous_names),
        "warnings": warnings,
    }
    return Graph(
        nodes=nodes,
        edges=edge_list,
        documents=documents,
        unlinked_relations=unlinked_relations,
        unlinked_facts=unlinked_facts,
        metadata=metadata,
    )


@dataclass(frozen=True)
class _Endpoint:
    """How one edge endpoint resolved against the node index."""

    name: str
    node_id: Optional[str]
    ambiguous: bool
    found: bool


class _NameIndex:
    """Node lookup by id and by normalized name or alias."""

    def __init__(self, nodes: List[Node]) -> None:
        self._by_id = {node.id: node for node in nodes}
        self._by_key: Dict[str, List[str]] = {}
        for node in nodes:
            for key in node.name_keys():
                bucket = self._by_key.setdefault(key, [])
                if node.id not in bucket:
                    bucket.append(node.id)

    def resolve(self, name: str, explicit_id: Optional[str]) -> _Endpoint:
        """Prefer an explicit id, then a unique name/alias match."""

        if explicit_id and explicit_id in self._by_id:
            return _Endpoint(name, explicit_id, False, True)
        matches = self._by_key.get(match_key(name), [])
        if len(matches) == 1:
            return _Endpoint(name, matches[0], False, True)
        if len(matches) > 1:
            return _Endpoint(name, None, True, True)
        return _Endpoint(name, None, False, False)


def _add_node(nodes_by_id: Dict[str, Node], kind: str, item: Any) -> None:
    metadata: Dict[str, Any] = {
        "description": item.description,
        SOURCES_KEY: list(item.sources),
    }
    if kind == KIND_ENTITY:
        metadata["type"] = item.type or ENTITY_TYPE_OTHER
    node = Node(
        id=item.id,
        kind=kind,
        title=item.name,
        aliases=tuple(item.aliases),
        metadata=metadata,
    )
    existing = nodes_by_id.get(node.id)
    if existing is None:
        nodes_by_id[node.id] = node
        return

    description = existing.metadata.get("description") or ""
    if len(node.metadata.get("description") or "") > len(description):
        description = node.metadata["description"]
    merged_metadata = dict(existing.metadata)
    merged_metadata["description"] = description
    merged_metadata[SOURCES_KEY] = merge_source_refs(
        existing.metadata.get(SOURCES_KEY, []), node.metadata.get(SOURCES_KEY, [])
    )
    if not merged_metadata.get("type") and node.metadata.get("type"):
        merged_metadata["type"] = node.metadata["type"]
    nodes_by_id[node.id] = replace(
        existing,
        aliases=_merge_aliases(existing, node),
        metadata=merged_metadata,
    )


def _merge_aliases(existing: Node, incoming: Node) -> Tuple[str, ...]:
    """Union of both name sets, without the canonical title."""

    canonical = match_key(existing.title)
    aliases: List[str] = []
    seen = {canonical}
    for node in (existing, incoming):
        for name in (node.title, *node.aliases):
            key = match_key(name)
            if key and key not in seen:
                seen.add(key)
                aliases.append(name)
    return tuple(aliases)


def _add_edge(edges: Dict[Tuple[str, str, str], Edge], edge: Edge) -> None:
    identity = edge_identity(edge)
    existing = edges.get(identity)
    edges[identity] = edge if existing is None else merge_edges(existing, edge)


def _note_ambiguity(endpoint: _Endpoint, ambiguous_names: set) -> None:
    if endpoint.ambiguous:
        ambiguous_names.add(match_key(endpoint.name))


def _unlinked_message(
    kind: str,
    source_name: str,
    source: _Endpoint,
    target_name: str,
    target: _Endpoint,
) -> str:
    problems = []
    if not source.found:
        problems.append(f"source {source_name!r} matches no node")
    elif source.ambiguous:
        problems.append(f"source {source_name!r} is ambiguous")
    if not target.found:
        problems.append(f"target {target_name!r} matches no node")
    elif target.ambiguous:
        problems.append(f"target {target_name!r} is ambiguous")
    return f"{kind} {source_name!r} -> {target_name!r} kept unlinked: " + "; ".join(
        problems
    )
