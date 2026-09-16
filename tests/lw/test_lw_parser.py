"""Mermaid subset parser tests."""

from __future__ import annotations

import pytest

from compiler.lw import MermaidEdge, MermaidNode, MermaidParseError, parse_mermaid


def test_basic_graph_with_implicit_nodes() -> None:
    document = parse_mermaid("graph TD\n    A --> B\n", source="basic.lw")

    assert document.direction == "TD"
    assert [node.id for node in document.nodes] == ["A", "B"]
    assert document.node("A") == MermaidNode(id="A", label="", line=2, column=5)
    assert document.edges == [
        MermaidEdge(source="A", target="B", label="", line=2, column=5)
    ]
    assert document.source == "basic.lw"
    assert document.metadata["parser"] == "lw-mermaid-subset-v1"


def test_node_label() -> None:
    document = parse_mermaid("graph TD\n    A[Parser]\n")

    assert document.nodes[0].label == "Parser"
    assert document.nodes[0].display_name == "Parser"


def test_quoted_node_label() -> None:
    document = parse_mermaid('graph TD\n    A["Parser core"]\n')

    assert document.nodes[0].label == "Parser core"


def test_edge_label() -> None:
    document = parse_mermaid("graph TD\n    A -->|produces| B\n")

    assert document.edges[0].label == "produces"


def test_edge_label_dash_form() -> None:
    document = parse_mermaid("graph TD\n    A -- produces --> B\n")

    assert document.edges[0].label == "produces"


@pytest.mark.parametrize("direction", ["TD", "TB", "LR", "RL", "BT"])
def test_every_direction(direction: str) -> None:
    document = parse_mermaid(f"graph {direction}\n    A --> B\n")

    assert document.direction == direction


def test_flowchart_keyword_and_lower_case_direction() -> None:
    document = parse_mermaid("flowchart lr\n    A --> B\n")

    assert document.direction == "LR"


def test_chained_edges() -> None:
    document = parse_mermaid("graph TD\n    A --> B --> C --> D\n")

    assert [node.id for node in document.nodes] == ["A", "B", "C", "D"]
    assert [(edge.source, edge.target) for edge in document.edges] == [
        ("A", "B"),
        ("B", "C"),
        ("C", "D"),
    ]


def test_chinese_labels() -> None:
    document = parse_mermaid(
        "graph TD\n    A[解析器]\n    B[文档模型]\n    A -->|产生| B\n"
    )

    assert [node.label for node in document.nodes] == ["解析器", "文档模型"]
    assert document.edges[0].label == "产生"


def test_bidirectional_edge_becomes_two_directed_edges() -> None:
    document = parse_mermaid("graph LR\n    A <--> B\n")

    assert [
        (edge.source, edge.target, edge.bidirectional) for edge in document.edges
    ] == [("A", "B", True), ("B", "A", True)]


def test_comments_and_blank_lines_are_ignored() -> None:
    document = parse_mermaid(
        "%% a comment\n\ngraph TD\n\n    %% another\n    A --> B\n"
    )

    assert [node.id for node in document.nodes] == ["A", "B"]


def test_semicolon_separates_statements() -> None:
    document = parse_mermaid("graph TD\n    A --> B; B --> C\n")

    assert [(edge.source, edge.target) for edge in document.edges] == [
        ("A", "B"),
        ("B", "C"),
    ]


def test_crlf_input() -> None:
    document = parse_mermaid("graph TD\r\n    A --> B\r\n")

    assert len(document.edges) == 1
    assert document.edges[0].line == 2


def test_duplicate_node_keeps_the_first_label_and_records_the_conflict() -> None:
    document = parse_mermaid("graph TD\n    A[Parser]\n    A[解析器]\n")

    assert len(document.nodes) == 1
    assert document.nodes[0].label == "Parser"
    assert document.metadata["label_conflicts"] == [
        {"id": "A", "kept": "Parser", "ignored": "解析器"}
    ]


def test_label_declared_after_the_edge_is_filled_in() -> None:
    document = parse_mermaid("graph TD\n    A --> B\n    A[Parser]\n")

    assert document.node("A").label == "Parser"


def test_identifier_stops_before_the_link_operator() -> None:
    document = parse_mermaid("graph TD\n    my-node --> other-node\n")

    assert [node.id for node in document.nodes] == ["my-node", "other-node"]


def test_empty_file_is_reported_with_a_location() -> None:
    with pytest.raises(MermaidParseError) as error:
        parse_mermaid("", source="empty.lw")

    assert error.value.line == 1
    assert error.value.column == 1
    assert "missing graph declaration" in str(error.value)
    assert str(error.value).startswith("ParseError: empty.lw:1:1")


def test_statement_before_the_header_is_reported() -> None:
    with pytest.raises(MermaidParseError) as error:
        parse_mermaid("A --> B\n", source="bad.lw")

    assert error.value.line == 1
    assert "missing graph declaration" in str(error.value)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("graph TD\n    A --> --> B\n", "expected a node id"),
        ("graph TD\n    A[Parser\n", "unterminated node label"),
        ("graph TD\n    A -->|produces B\n", "unterminated edge label"),
        ("graph TD\n    A(Parser)\n", "node shape '(' is not supported"),
        ("graph TD\n    A -.-> B\n", "link operator '-.->' is not supported"),
        ("graph TD\n    A --- B\n", "link operator '---' is not supported"),
        ("graph TD\n    A ==> B\n", "link operator '==>' is not supported"),
        ("graph QQ\n    A --> B\n", "unsupported direction 'QQ'"),
        ("graph\n    A --> B\n", "'graph' needs a direction"),
        ("graph TD extra\n    A --> B\n", "unexpected text after the direction"),
        (
            "sequenceDiagram\n    A->>B: hi\n",
            "diagram type 'sequenceDiagram' is not supported",
        ),
        ("graph TD\n    subgraph RAG\n", "Mermaid feature 'subgraph' is not support"),
        ("graph TD\n    style A fill:#f00\n", "Mermaid feature 'style' is not support"),
        ("graph TD\n    click A href \"x\"\n", "Mermaid feature 'click' is not support"),
        ("graph TD\n    classDef red fill:#f00\n", "'classDef' is not support"),
        ("graph TD\n    direction LR\n", "Mermaid feature 'direction' is not support"),
        ("graph TD\n%%{init: {}}%%\n", "Mermaid directives"),
    ],
)
def test_unsupported_syntax_is_reported(text: str, expected: str) -> None:
    with pytest.raises(MermaidParseError) as error:
        parse_mermaid(text, source="example.lw")

    assert expected in str(error.value)
    assert f"example.lw:{error.value.line}:{error.value.column}" in str(error.value)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "A",
        "graph",
        "graph TD\n-->",
        "graph TD\nA[",
        "graph TD\nA -->|",
        "graph TD\n<--> B",
        "graph TD\nA --> B -->",
        "graph TD\nA(B)",
        "graph TD\nA ==> B",
        "graph TD\nA --> B\n%%{x}%%",
    ],
)
def test_malformed_input_never_leaks_low_level_errors(text: str) -> None:
    try:
        parse_mermaid(text)
    except MermaidParseError:
        pass
    except Exception as unexpected:  # pragma: no cover - safety net
        pytest.fail(f"unexpected {type(unexpected).__name__}: {unexpected}")
