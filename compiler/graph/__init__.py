"""Stage 8 of the LLM Wiki Compiler: the knowledge graph.

Builds a plain in-memory graph from a KnowledgeBase::

    >>> from compiler.graph import build_graph
    >>> graph = build_graph(knowledge_base)
    >>> [node.title for node in graph.get_nodes()]
    ['解析器', '文档模型']
    >>> graph.neighbors(graph.get_node("a7755ec09b9f5bed").id)
    [Node(id='5696d7c87b3ba71a', kind='concept', title='文档模型', ...)]

Nodes are entities and concepts (identity is the ``object_id``), edges are
relations - plus facts that carry a complete subject/predicate/object triple.
Edge endpoints keep the names as written, with resolved node ids in metadata.
Nothing is re-parsed: the graph is built from structured knowledge, never from
Markdown, and never calls an LLM.
"""

from .builder import GRAPH_BUILDER_VERSION, build_graph
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

__all__ = [
    "Edge",
    "GRAPH_BUILDER_VERSION",
    "Graph",
    "KIND_CONCEPT",
    "KIND_ENTITY",
    "KIND_FACT",
    "KIND_RELATION",
    "Node",
    "SOURCES_KEY",
    "build_graph",
    "edge_identity",
    "edge_sort_key",
    "merge_edges",
    "merge_source_refs",
    "node_sort_key",
]
