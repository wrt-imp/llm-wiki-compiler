"""Graph data structure and serialization tests."""

from __future__ import annotations

import json

from compiler.graph import (
    KIND_CONCEPT,
    KIND_ENTITY,
    Edge,
    Graph,
    Node,
    edge_identity,
    edge_sort_key,
    merge_edges,
    merge_source_refs,
    node_sort_key,
)
from compiler.knowledge import SourceRef
from support import src_ref


def sample_graph() -> Graph:
    parser = Node(
        id="e1",
        kind=KIND_ENTITY,
        title="解析器",
        aliases=("Parser",),
        metadata={"type": "system", "description": "组件", "sources": [src_ref("docA")]},
    )
    model = Node(
        id="c1",
        kind=KIND_CONCEPT,
        title="文档模型",
        metadata={"description": "结构", "sources": [src_ref("docB")]},
    )
    edge = Edge(
        source="解析器",
        target="文档模型",
        type="produces",
        kind="relation",
        metadata={
            "source_id": "e1",
            "target_id": "c1",
            "description": "产出文档模型",
            "statements": [],
            "kinds": ["relation"],
            "sources": [src_ref("docA", quote="解析器产出文档模型")],
        },
    )
    return Graph(
        nodes=[parser, model],
        edges=[edge],
        documents=[{"id": "docA", "title": "t", "source": "a.md"}],
        metadata={"builder_version": "test"},
    )


def test_node_name_keys_include_title_and_aliases() -> None:
    node = Node(id="e1", kind=KIND_ENTITY, title="Parser", aliases=("解析器",))

    assert node.name_keys() == ["parser", "解析器"]


def test_edge_identity_ignores_case_and_spacing() -> None:
    first = Edge(source="Parser", target="Document Model", type="Produces", kind="relation")
    second = Edge(source="parser", target="document   model", type="produces", kind="fact")

    assert edge_identity(first) == edge_identity(second)


def test_edge_self_loop_flag() -> None:
    assert Edge(source="解析器", target="解析器", type="uses", kind="relation").is_self_loop
    assert not Edge(source="a", target="b", type="uses", kind="relation").is_self_loop


def test_merge_edges_unions_sources_and_kinds() -> None:
    relation = Edge(
        source="a",
        target="b",
        type="uses",
        kind="relation",
        metadata={"kinds": ["relation"], "sources": [src_ref("docA", quote="q1")]},
    )
    fact = Edge(
        source="a",
        target="b",
        type="uses",
        kind="fact",
        metadata={
            "kinds": ["fact"],
            "sources": [src_ref("docB", quote="q2")],
            "statements": ["a uses b"],
        },
    )

    merged = merge_edges(relation, fact)

    assert merged.kind == "relation"
    assert merged.metadata["kinds"] == ["fact", "relation"]
    assert [source.quote for source in merged.metadata["sources"]] == ["q1", "q2"]
    assert merged.metadata["statements"] == ["a uses b"]


def test_merge_source_refs_deduplicates() -> None:
    first = src_ref("docA", section_id="docA#1", quote="q")
    duplicate = src_ref("docA", section_id="docA#1", quote="q")
    second = src_ref("docB", quote="other")

    assert merge_source_refs([first], [duplicate, second]) == [first, second]


def test_sort_keys_are_stable() -> None:
    entity = Node(id="e1", kind=KIND_ENTITY, title="解析器")
    concept = Node(id="c1", kind=KIND_CONCEPT, title="文档模型")
    edge_b = Edge(source="b", target="c", type="uses", kind="relation")
    edge_a = Edge(source="a", target="c", type="uses", kind="relation")

    assert sorted([concept, entity], key=node_sort_key)[0] is entity
    assert sorted([edge_b, edge_a], key=edge_sort_key)[0] is edge_a


def test_serialization_round_trip() -> None:
    graph = sample_graph()

    restored = Graph.from_dict(json.loads(json.dumps(graph.to_dict())))

    assert restored == graph
    assert isinstance(restored.nodes[0].metadata["sources"][0], SourceRef)
    assert restored.edges[0].metadata["source_id"] == "e1"


def test_to_dict_is_json_friendly() -> None:
    payload = sample_graph().to_dict()

    assert payload["nodes"][0]["aliases"] == ["Parser"]
    assert payload["nodes"][0]["metadata"]["sources"][0]["document_id"] == "docA"
    assert payload["edges"][0]["source"] == "解析器"
    assert json.dumps(payload, ensure_ascii=False)


def test_get_node_and_getters() -> None:
    graph = sample_graph()

    assert graph.get_node("e1").title == "解析器"
    assert graph.get_node("missing") is None
    assert [node.id for node in graph.get_nodes()] == ["e1", "c1"]
    assert [edge.type for edge in graph.get_edges()] == ["produces"]


def test_queries_on_unknown_nodes_are_empty() -> None:
    graph = sample_graph()

    assert graph.neighbors("nope") == []
    assert graph.incoming("nope") == []
    assert graph.outgoing("nope") == []
