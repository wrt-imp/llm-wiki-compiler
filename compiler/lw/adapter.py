"""Turn a parsed Mermaid document into the project's :class:`Graph`.

This is the only place where the two layers meet: the parsed model describes
how the source file is written, the graph describes what the graph is. Nodes
keep the Mermaid id as identity (``Node.id``) and the label as the display
title, so ``A[解析器]`` never turns the label into an id.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from ..graph import (
    Edge,
    Graph,
    Node,
    edge_identity,
    edge_sort_key,
    merge_edges,
    node_sort_key,
)
from .model import MermaidDocument, MermaidNode

LW_ADAPTER_VERSION = "lw-graph-v1"

#: Kind used for nodes that come from a ``.lw`` graph source.
LW_NODE_KIND = "lw"
#: Edges stay in the existing relation vocabulary.
LW_EDGE_KIND = "relation"


def to_graph(document: MermaidDocument, *, source: Optional[str] = None) -> Graph:
    """Convert a parsed Mermaid document into a :class:`Graph`.

    The document is only read; the returned graph is a fresh object.

    Raises:
        TypeError: when the input is not a :class:`MermaidDocument`.
    """

    if not isinstance(document, MermaidDocument):
        raise TypeError(
            "to_graph expects a MermaidDocument, got "
            f"{type(document).__name__}"
        )

    source_name = source if source is not None else document.source
    warnings: List[str] = []

    nodes: Dict[str, Node] = {}
    for mermaid_node in document.nodes:
        node = _build_node(mermaid_node, source_name)
        existing = nodes.get(node.id)
        nodes[node.id] = node if existing is None else _merge_nodes(existing, node)

    _apply_label_conflicts(document, nodes)

    edges: Dict[Tuple[str, str, str], Edge] = {}
    for mermaid_edge in document.edges:
        for endpoint in (mermaid_edge.source, mermaid_edge.target):
            if endpoint not in nodes:
                nodes[endpoint] = _build_node(
                    MermaidNode(
                        id=endpoint,
                        label="",
                        line=mermaid_edge.line,
                        column=mermaid_edge.column,
                    ),
                    source_name,
                )
                warnings.append(
                    f"edge endpoint {endpoint!r} had no node declaration; "
                    "it was added to the graph"
                )
        edge = _build_edge(mermaid_edge, source_name)
        identity = edge_identity(edge)
        existing_edge = edges.get(identity)
        edges[identity] = (
            edge if existing_edge is None else merge_edges(existing_edge, edge)
        )

    node_list = sorted(nodes.values(), key=node_sort_key)
    edge_list = sorted(edges.values(), key=edge_sort_key)
    metadata: Dict[str, Any] = {
        "builder_version": LW_ADAPTER_VERSION,
        "source": source_name,
        "direction": document.direction,
        "nodes": len(node_list),
        "edges": len(edge_list),
        "self_loops": sum(1 for edge in edge_list if edge.is_self_loop),
        "warnings": warnings,
    }
    return Graph(
        nodes=node_list,
        edges=edge_list,
        documents=[],
        unlinked_relations=[],
        unlinked_facts=[],
        metadata=metadata,
    )


def _build_node(mermaid_node: MermaidNode, source_name: str) -> Node:
    return Node(
        id=mermaid_node.id,
        kind=LW_NODE_KIND,
        title=mermaid_node.display_name,
        aliases=(),
        metadata={
            "origin": "lw",
            "description": "",
            "sources": [],
            "source": source_name,
            "line": mermaid_node.line,
        },
    )


def _merge_nodes(existing: Node, incoming: Node) -> Node:
    aliases = list(existing.aliases)
    for name in (existing.title, incoming.title):
        if name and name != existing.title and name not in aliases:
            aliases.append(name)
    return replace(existing, aliases=tuple(aliases))


def _apply_label_conflicts(
    document: MermaidDocument, nodes: Dict[str, Node]
) -> None:
    """Labels that lost to an earlier declaration stay reachable as aliases."""

    for conflict in document.metadata.get("label_conflicts", []):
        node = nodes.get(str(conflict.get("id", "")))
        ignored = str(conflict.get("ignored", ""))
        if node is None or not ignored or ignored in node.aliases:
            continue
        nodes[node.id] = replace(node, aliases=(*node.aliases, ignored))


def _build_edge(mermaid_edge: Any, source_name: str) -> Edge:
    return Edge(
        source=mermaid_edge.source,
        target=mermaid_edge.target,
        type=mermaid_edge.label or "",
        kind=LW_EDGE_KIND,
        metadata={
            "source_id": mermaid_edge.source,
            "target_id": mermaid_edge.target,
            "description": "",
            "statements": [],
            "kinds": [LW_EDGE_KIND],
            "sources": [],
            "origin": "lw",
            "source": source_name,
            "line": mermaid_edge.line,
            "bidirectional": bool(mermaid_edge.bidirectional),
        },
    )
