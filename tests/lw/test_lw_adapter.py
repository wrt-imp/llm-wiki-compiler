"""Mermaid parsed model -> project Graph adapter tests."""

from __future__ import annotations

import json

import pytest

from compiler.graph import Graph
from compiler.lint import lint
from compiler.lw import (
    LW_NODE_KIND,
    MermaidDocument,
    MermaidEdge,
    parse_mermaid,
    to_graph,
)

SOURCE = (
    "graph TD\n"
    "    Parser[解析器]\n"
    "    DocumentModel[文档模型]\n"
    "    Parser -->|produces| DocumentModel\n"
)


def sample_graph() -> Graph:
    return to_graph(parse_mermaid(SOURCE, source="example.lw"), source="example.lw")


def test_nodes_keep_the_mermaid_id_and_label() -> None:
    graph = sample_graph()
    parser = graph.get_node("Parser")

    assert parser.kind == LW_NODE_KIND
    assert parser.id == "Parser"
    assert parser.title == "解析器"
    assert parser.metadata["origin"] == "lw"
    assert parser.metadata["line"] == 2
    assert graph.get_node("DocumentModel").title == "文档模型"


def test_edge_keeps_the_label_as_type() -> None:
    edge = sample_graph().get_edges()[0]

    assert (edge.source, edge.type, edge.target) == ("Parser", "produces", "DocumentModel")
    assert edge.kind == "relation"
    assert edge.metadata["source_id"] == "Parser"
    assert edge.metadata["target_id"] == "DocumentModel"
    assert edge.metadata["line"] == 4


def test_missing_edge_label_stays_empty() -> None:
    graph = to_graph(parse_mermaid("graph TD\n    A --> B\n"))

    assert graph.get_edges()[0].type == ""


def test_implicit_endpoints_are_added_with_a_warning() -> None:
    document = MermaidDocument(
        direction="TD", edges=[MermaidEdge("A", "B", "")]
    )

    graph = to_graph(document)

    assert sorted(node.id for node in graph.get_nodes()) == ["A", "B"]
    assert any("no node declaration" in warning for warning in graph.metadata["warnings"])


def test_bidirectional_edges_stay_two_edges() -> None:
    graph = to_graph(parse_mermaid("graph LR\n    A <--> B\n"))

    assert [(edge.source, edge.target) for edge in graph.get_edges()] == [
        ("A", "B"),
        ("B", "A"),
    ]
    assert all(edge.metadata["bidirectional"] for edge in graph.get_edges())


def test_duplicate_edges_are_merged() -> None:
    graph = to_graph(
        parse_mermaid("graph TD\n    A -->|x| B\n    A -->|x| B\n")
    )

    assert len(graph.get_edges()) == 1


def test_self_loop_is_kept() -> None:
    graph = to_graph(parse_mermaid("graph TD\n    A --> A\n"))

    assert graph.get_edges()[0].is_self_loop is True
    assert graph.metadata["self_loops"] == 1


def test_label_conflict_becomes_an_alias() -> None:
    graph = to_graph(parse_mermaid("graph TD\n    A[Parser]\n    A[解析器]\n"))

    node = graph.get_node("A")
    assert node.title == "Parser"
    assert node.aliases == ("解析器",)


def test_metadata_describes_the_graph() -> None:
    metadata = sample_graph().metadata

    assert metadata["builder_version"] == "lw-graph-v1"
    assert metadata["source"] == "example.lw"
    assert metadata["direction"] == "TD"
    assert metadata["nodes"] == 2
    assert metadata["edges"] == 1
    assert metadata["self_loops"] == 0
    assert metadata["warnings"] == []


def test_graph_queries_work_on_a_lw_graph() -> None:
    graph = sample_graph()

    assert [node.title for node in graph.neighbors("DocumentModel")] == ["解析器"]
    assert len(graph.outgoing("Parser")) == 1
    assert len(graph.incoming("DocumentModel")) == 1
    assert graph.incoming("Parser") == []


def test_document_is_not_modified() -> None:
    document = parse_mermaid(SOURCE, source="example.lw")
    before = document.to_dict()

    to_graph(document, source="example.lw")

    assert document.to_dict() == before


def test_building_twice_is_stable() -> None:
    document = parse_mermaid(SOURCE, source="example.lw")

    first = to_graph(document, source="example.lw")
    second = to_graph(document, source="example.lw")

    assert json.dumps(first.to_dict(), ensure_ascii=False) == json.dumps(
        second.to_dict(), ensure_ascii=False
    )


def test_rejects_input_that_is_not_a_document() -> None:
    with pytest.raises(TypeError) as error:
        to_graph("graph TD\n A --> B\n")

    assert "MermaidDocument" in str(error.value)


def test_graph_serialization_round_trip() -> None:
    graph = sample_graph()

    restored = Graph.from_dict(json.loads(json.dumps(graph.to_dict(), ensure_ascii=False)))

    assert restored == graph


def test_lint_accepts_a_lw_graph() -> None:
    clean = lint(graph=sample_graph())

    assert clean.issues == []
    assert clean.is_clean() is True


def test_lint_reports_self_loops_as_info_only() -> None:
    result = lint(graph=to_graph(parse_mermaid("graph TD\n    A --> A\n")))

    assert result.counts["errors"] == 0
    assert result.counts["self_loops"] == 1
    assert result.issues[0].severity == "info"
