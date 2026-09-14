"""Document Model tests: structure, ids and serialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from compiler.document import (
    SECTION_KIND_HEADING,
    Document,
    Section,
    load_document,
    make_section_id,
)


def sample_document() -> Document:
    child = Section(
        id="doc#1.1",
        title="子章节",
        content="子章节内容",
        level=2,
        metadata={"kind": SECTION_KIND_HEADING, "line_start": 3, "line_end": 4},
    )
    root = Section(
        id="doc#1",
        title="章节",
        content="章节正文",
        level=1,
        children=[child],
        metadata={"kind": SECTION_KIND_HEADING, "line_start": 1, "line_end": 2},
    )
    return Document(
        id="doc",
        title="标题",
        source="notes.md",
        format="markdown",
        content="章节正文\n子章节内容",
        sections=[root],
        metadata={"encoding": "utf-8"},
    )


def test_section_fields_and_nesting() -> None:
    root = sample_document().sections[0]

    assert root.title == "章节"
    assert root.content == "章节正文"
    assert root.level == 1
    assert [child.title for child in root.children] == ["子章节"]
    assert root.children[0].level == 2
    assert root.children[0].children == []
    assert root.metadata["kind"] == SECTION_KIND_HEADING


def test_document_sections_default_to_empty() -> None:
    document = Document(
        id="doc", title="t", source="s.txt", format="txt", content="body"
    )

    assert document.sections == []
    assert document.metadata == {}


def test_walk_sections_is_depth_first() -> None:
    document = sample_document()

    assert [section.title for section in document.walk_sections()] == [
        "章节",
        "子章节",
    ]


def test_find_section_by_id() -> None:
    document = sample_document()

    assert document.find_section("doc#1.1").content == "子章节内容"
    assert document.find_section("doc#nope") is None
    assert document.sections[0].find("doc#1") is document.sections[0]


def test_section_id_is_document_id_plus_ordinal_path() -> None:
    assert make_section_id("d5ea7f9579c3e970", "2.1") == "d5ea7f9579c3e970#2.1"


def test_serialization_round_trip() -> None:
    document = sample_document()

    restored = Document.from_dict(json.loads(json.dumps(document.to_dict())))

    assert restored == document
    assert restored.sections[0].children[0].title == "子章节"


def test_to_dict_returns_copies() -> None:
    document = sample_document()

    snapshot = document.to_dict()
    snapshot["metadata"]["mutated"] = True
    snapshot["sections"][0]["children"][0]["title"] = "changed"

    assert "mutated" not in document.metadata
    assert document.sections[0].children[0].title == "子章节"


def test_parser_layer_shares_the_same_document_class() -> None:
    import compiler.parser as parser_layer

    assert parser_layer.Document is Document


def test_load_document_assigns_stable_ids(
    text_file: Callable[..., Path]
) -> None:
    path = text_file("stable.txt", "标题行\n\n正文\n")

    first = load_document(path)
    second = load_document(path)

    assert first.id == second.id
    assert first.sections[0].id == second.sections[0].id
    assert first.sections[0].id.startswith(f"{first.id}#")
