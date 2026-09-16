"""A deliberately small Mermaid graph parser.

Supported subset::

    graph TD | flowchart LR            direction: TD TB LR RL BT
    A                                  bare node (edge endpoints are implicit)
    A[Label] / A["Label"]              node with a display label
    A --> B                            directed edge
    A -->|label| B                     edge with a relation label
    A -- label --> B                   same, the other common spelling
    A <--> B                           bidirectional -> two directed edges
    A --> B --> C                      chained edges
    %% comment                         comment to the end of the line
    A --> B; B --> C                   ";" separates statements

Everything outside that subset is rejected with a located error, so the user
never sees an ``IndexError`` or ``KeyError``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterator, List, Tuple

from .errors import MermaidParseError
from .model import MermaidDocument, MermaidEdge, MermaidNode

PARSER_VERSION = "lw-mermaid-subset-v1"

DIRECTIONS = ("TD", "TB", "LR", "RL", "BT")
HEADER_KEYWORDS = ("graph", "flowchart")

#: Features that Mermaid knows but this version does not support.
UNSUPPORTED_KEYWORDS = (
    "subgraph",
    "end",
    "style",
    "classdef",
    "class",
    "click",
    "linkstyle",
    "direction",
)

#: Other Mermaid diagram types.
UNSUPPORTED_DIAGRAMS = (
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "statediagram-v2",
    "erdiagram",
    "gantt",
    "pie",
    "journey",
    "mindmap",
    "timeline",
    "gitgraph",
    "quadrantchart",
    "xychart-beta",
    "sankey-beta",
    "block-beta",
    "packet-beta",
    "architecture-beta",
    "requirementdiagram",
    "c4context",
)

_LINK_OPERATORS = ("<-->", "-->", "--", "==>", "-.->", "---", "~~~", "o--o", "x--x")
_UNSUPPORTED_LINK_OPERATORS = ("==>", "-.->", "---", "~~~", "-.-", "===")
_ID_EXTRA = "_.-:#"
_ID_STOP_CHARS = "[](){}|;,=&"


@dataclass(frozen=True)
class _NodeRef:
    id: str
    label: str


@dataclass(frozen=True)
class _Link:
    label: str
    bidirectional: bool


def parse_mermaid(text: str, *, source: str = "") -> MermaidDocument:
    """Parse a ``.lw`` file body into a :class:`MermaidDocument`.

    Raises:
        MermaidParseError: when the source leaves the supported subset; the
            error always carries a line and a column.
    """

    if not isinstance(text, str):
        raise MermaidParseError(
            "source must be text", line=1, column=1, source=source
        )

    document = MermaidDocument(source=source)
    nodes: Dict[str, MermaidNode] = {}
    edges: List[MermaidEdge] = []
    conflicts: List[Dict[str, str]] = []
    header_seen = False

    for number, raw_line in enumerate(_lines(text), start=1):
        if raw_line.strip().startswith("%%{"):
            raise MermaidParseError(
                "Mermaid directives ('%%{...}%%') are not supported in this "
                "version",
                line=number,
                column=1,
                source=source,
            )
        for statement, column in _statements(raw_line):
            if not header_seen:
                _parse_header(statement, number, column, document, source)
                header_seen = True
                continue
            _parse_statement(
                statement, number, column, nodes, edges, conflicts, source
            )

    if not header_seen:
        raise MermaidParseError(
            "missing graph declaration; expected 'graph TD' as the first "
            "statement",
            line=1,
            column=1,
            source=source,
        )

    document.nodes = list(nodes.values())
    document.edges = edges
    document.metadata["parser"] = PARSER_VERSION
    if conflicts:
        document.metadata["label_conflicts"] = conflicts
    return document


def _parse_header(
    statement: str,
    line: int,
    column: int,
    document: MermaidDocument,
    source: str,
) -> None:
    tokens = statement.split()
    keyword = tokens[0]
    folded = keyword.casefold().rstrip(":")
    if folded in UNSUPPORTED_DIAGRAMS:
        raise MermaidParseError(
            f"diagram type {keyword!r} is not supported; only graph/flowchart "
            "are",
            line=line,
            column=column,
            source=source,
        )
    if folded not in HEADER_KEYWORDS:
        raise MermaidParseError(
            f"missing graph declaration; expected 'graph TD' but found "
            f"{keyword!r}",
            line=line,
            column=column,
            source=source,
        )
    if len(tokens) < 2:
        raise MermaidParseError(
            f"'{keyword}' needs a direction (one of {', '.join(DIRECTIONS)})",
            line=line,
            column=column + len(keyword),
            source=source,
        )
    if len(tokens) > 2:
        raise MermaidParseError(
            "unexpected text after the direction; put each statement on its "
            "own line",
            line=line,
            column=column + len(tokens[0]) + len(tokens[1]) + 1,
            source=source,
        )
    direction = tokens[1].upper()
    if direction not in DIRECTIONS:
        raise MermaidParseError(
            f"unsupported direction {tokens[1]!r}; expected one of "
            f"{', '.join(DIRECTIONS)}",
            line=line,
            column=column + len(keyword) + 1,
            source=source,
        )
    document.direction = direction


def _parse_statement(
    statement: str,
    line: int,
    column: int,
    nodes: Dict[str, MermaidNode],
    edges: List[MermaidEdge],
    conflicts: List[Dict[str, str]],
    source: str,
) -> None:
    keyword = statement.split(None, 1)[0].rstrip(":").casefold()
    if keyword in UNSUPPORTED_KEYWORDS:
        raise MermaidParseError(
            f"Mermaid feature {statement.split(None, 1)[0]!r} is not supported "
            "in this version",
            line=line,
            column=column,
            source=source,
        )
    if keyword in UNSUPPORTED_DIAGRAMS:
        raise MermaidParseError(
            f"diagram type {statement.split(None, 1)[0]!r} is not supported; "
            "only graph/flowchart are",
            line=line,
            column=column,
            source=source,
        )

    current, position = _read_node_ref(statement, 0, line, column, source)
    _add_node(nodes, current, line, column, conflicts)

    while True:
        position = _skip_space(statement, position)
        if position >= len(statement):
            return
        link, position = _read_link(statement, position, line, column, source)
        endpoint, position = _read_node_ref(statement, position, line, column, source)
        _add_node(nodes, endpoint, line, column, conflicts)
        edges.append(
            MermaidEdge(
                source=current.id,
                target=endpoint.id,
                label=link.label,
                bidirectional=link.bidirectional,
                line=line,
                column=column,
            )
        )
        if link.bidirectional:
            edges.append(
                MermaidEdge(
                    source=endpoint.id,
                    target=current.id,
                    label=link.label,
                    bidirectional=True,
                    line=line,
                    column=column,
                )
            )
        current = endpoint


def _read_node_ref(
    text: str, position: int, line: int, column: int, source: str
) -> Tuple[_NodeRef, int]:
    position = _skip_space(text, position)
    start = position
    identifier, position = _read_id(text, position)
    if not identifier:
        raise MermaidParseError(
            "expected a node id",
            line=line,
            column=column + start,
            source=source,
        )

    after_id = _skip_space(text, position)
    label = ""
    if after_id < len(text) and text[after_id] == "[":
        label, position = _read_label(text, after_id, line, column, source)
    elif after_id < len(text) and text[after_id] in "({":
        raise MermaidParseError(
            f"node shape {text[after_id]!r} is not supported; use 'A[Label]'",
            line=line,
            column=column + after_id,
            source=source,
        )
    else:
        position = after_id
    return _NodeRef(identifier, label), position


def _read_label(
    text: str, position: int, line: int, column: int, source: str
) -> Tuple[str, int]:
    end = text.find("]", position + 1)
    if end == -1:
        raise MermaidParseError(
            "unterminated node label: missing ']'",
            line=line,
            column=column + position,
            source=source,
        )
    label = text[position + 1 : end].strip()
    if len(label) >= 2 and label[0] == label[-1] and label[0] in "\"'":
        label = label[1:-1]
    return label, end + 1


def _read_link(
    text: str, position: int, line: int, column: int, source: str
) -> Tuple[_Link, int]:
    if text.startswith("<-->", position):
        return _Link("", True), position + 4

    for operator in _UNSUPPORTED_LINK_OPERATORS:
        if text.startswith(operator, position):
            raise MermaidParseError(
                f"link operator {operator!r} is not supported in this version; "
                "use '-->'",
                line=line,
                column=column + position,
                source=source,
            )

    if text.startswith("-->", position):
        label, position = _read_pipe_label(text, position + 3, line, column, source)
        return _Link(label, False), position

    if text.startswith("--", position):
        closing = text.find("-->", position + 2)
        if closing == -1:
            raise MermaidParseError(
                "unsupported or malformed link; expected '-->' or "
                "'-- label -->'",
                line=line,
                column=column + position,
                source=source,
            )
        label = text[position + 2 : closing].strip()
        return _Link(label, False), closing + 3

    raise MermaidParseError(
        "expected a link operator ('-->' or '-- label -->')",
        line=line,
        column=column + position,
        source=source,
    )


def _read_pipe_label(
    text: str, position: int, line: int, column: int, source: str
) -> Tuple[str, int]:
    position = _skip_space(text, position)
    if position >= len(text) or text[position] != "|":
        return "", position
    end = text.find("|", position + 1)
    if end == -1:
        raise MermaidParseError(
            "unterminated edge label: missing '|'",
            line=line,
            column=column + position,
            source=source,
        )
    return text[position + 1 : end].strip(), end + 1


def _read_id(text: str, position: int) -> Tuple[str, int]:
    start = position
    while position < len(text):
        if _starts_link(text, position):
            break
        character = text[position]
        if character.isspace() or character in _ID_STOP_CHARS:
            break
        if not (
            character.isalnum()
            or character in _ID_EXTRA
            or ord(character) > 0x2E80
        ):
            break
        position += 1
    return text[start:position], position


def _starts_link(text: str, position: int) -> bool:
    return any(text.startswith(operator, position) for operator in _LINK_OPERATORS)


def _add_node(
    nodes: Dict[str, MermaidNode],
    reference: _NodeRef,
    line: int,
    column: int,
    conflicts: List[Dict[str, str]],
) -> None:
    existing = nodes.get(reference.id)
    if existing is None:
        nodes[reference.id] = MermaidNode(
            id=reference.id, label=reference.label, line=line, column=column
        )
        return
    if reference.label and not existing.label:
        nodes[reference.id] = replace(existing, label=reference.label)
    elif reference.label and existing.label and reference.label != existing.label:
        conflicts.append(
            {"id": reference.id, "kept": existing.label, "ignored": reference.label}
        )


def _skip_space(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _lines(text: str) -> List[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.split("\n")


def _statements(line: str) -> Iterator[Tuple[str, int]]:
    """Split a line into ``;`` separated statements with 1-based columns."""

    body = _strip_comment(line)
    column = 1
    for piece in body.split(";"):
        stripped = piece.strip()
        if stripped:
            yield stripped, column + piece.index(stripped[0])
        column += len(piece) + 1


def _strip_comment(line: str) -> str:
    index = line.find("%%")
    return line if index == -1 else line[:index]
