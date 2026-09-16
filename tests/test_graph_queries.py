"""Graph query tests."""

from __future__ import annotations

from compiler.graph import build_graph
from compiler.knowledge import make_knowledge_id
from support import concept, entity, make_kb, relation, src_ref


def parser_id() -> str:
    return make_knowledge_id("entity", "解析器")


def model_id() -> str:
    return make_knowledge_id("concept", "文档模型")


def sample_graph():
    kb = make_kb(
        entities=(
            entity("解析器", aliases=("Parser",), sources=(src_ref("docA", quote="q1"),)),
            entity("知识图谱编译器"),
        ),
        concepts=(concept("文档模型"),),
        relations=(
            relation("解析器", "文档模型", type="produces"),
            relation("知识图谱编译器", "解析器", type="uses"),
            relation("解析器", "解析器", type="depends on"),
        ),
    )
    return build_graph(kb)


def test_neighbors_include_both_directions() -> None:
    graph = sample_graph()

    titles = [node.title for node in graph.neighbors(parser_id())]

    # entities first (sorted by name), then concepts
    assert titles == ["知识图谱编译器", "解析器", "文档模型"]


def test_outgoing_edges() -> None:
    graph = sample_graph()

    edges = graph.outgoing(parser_id())

    assert sorted(edge.type for edge in edges) == ["depends on", "produces"]
    assert all(edge.source == "解析器" for edge in edges)


def test_incoming_edges() -> None:
    graph = sample_graph()

    edges = graph.incoming(parser_id())

    assert sorted(edge.type for edge in edges) == ["depends on", "uses"]
    assert all(edge.target == "解析器" for edge in edges)


def test_self_loop_appears_once_in_neighbors() -> None:
    graph = sample_graph()

    neighbors = graph.neighbors(parser_id())
    ids = [node.id for node in neighbors]

    assert ids.count(parser_id()) == 1
    assert len(ids) == len(set(ids))


def test_neighbors_of_a_leaf() -> None:
    graph = sample_graph()

    assert [node.title for node in graph.neighbors(model_id())] == ["解析器"]


def test_neighbors_are_sorted_deterministically() -> None:
    graph = sample_graph()

    first = [node.id for node in graph.neighbors(parser_id())]
    second = [node.id for node in graph.neighbors(parser_id())]

    assert first == second
    assert first == sorted(
        first,
        key=lambda node_id: (
            {"entity": 0, "concept": 1}[graph.get_node(node_id).kind],
            graph.get_node(node_id).title,
            node_id,
        ),
    )


def test_edges_are_sorted_deterministically() -> None:
    graph = sample_graph()

    assert graph.get_edges() == graph.get_edges()
    assert [edge.source for edge in graph.get_edges()] == sorted(
        edge.source for edge in graph.get_edges()
    )


def test_queries_are_read_only() -> None:
    graph = sample_graph()
    before = graph.to_dict()

    graph.neighbors(parser_id())
    graph.incoming(parser_id())
    graph.outgoing(parser_id())

    assert graph.to_dict() == before


def test_graph_of_a_merged_knowledge_base() -> None:
    kb = make_kb(
        entities=(
            entity("解析器", aliases=("Parser",), sources=(src_ref("docA", quote="q1"),)),
        ),
        concepts=(concept("文档模型", sources=(src_ref("docB", quote="q2"),)),),
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="produces",
                sources=(src_ref("docA", quote="q3"), src_ref("docB", quote="q4")),
            ),
        ),
    )

    graph = build_graph(kb)
    edge = graph.get_edges()[0]

    assert len(graph.get_nodes()) == 2
    assert len(edge.metadata["sources"]) == 2
    assert edge.metadata["sources"][0].document_id == "docA"
