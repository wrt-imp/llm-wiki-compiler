"""Parsing and validation tests for the LLM answer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from compiler.document import load_document
from compiler.extraction import (
    InvalidPayloadError,
    InvalidResponseError,
    parse_llm_json,
    validate_payload,
)
from support import empty_payload, sample_payload, source

MARKDOWN_SAMPLE = "# 总览\n\n解析器把 PDF、Markdown、TXT 统一成 Document。\n"


def test_parses_a_plain_json_object() -> None:
    payload, warnings = parse_llm_json('{"entities": [], "concepts": []}')

    assert payload == {"entities": [], "concepts": []}
    assert warnings == []


def test_strips_markdown_code_fences() -> None:
    payload, warnings = parse_llm_json('```json\n{"entities": []}\n```')

    assert payload == {"entities": []}
    assert any("code fence" in warning for warning in warnings)


def test_ignores_text_around_the_json_object() -> None:
    raw = 'Here is the result:\n{"entities": []}\nHope that helps!'

    payload, warnings = parse_llm_json(raw)

    assert payload == {"entities": []}
    assert any("around the JSON" in warning for warning in warnings)


def test_rejects_invalid_json() -> None:
    with pytest.raises(InvalidResponseError) as error:
        parse_llm_json("{not json at all")

    assert "not valid JSON" in str(error.value)


def test_rejects_an_empty_response() -> None:
    with pytest.raises(InvalidResponseError):
        parse_llm_json("   \n ")


def test_rejects_json_that_is_not_an_object() -> None:
    with pytest.raises(InvalidResponseError) as error:
        parse_llm_json('[{"entities": []}]')

    assert "must be a JSON object" in str(error.value)


def test_valid_payload_becomes_knowledge_ir(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    section = document.sections[0]

    knowledge, warnings = validate_payload(
        sample_payload(section.id, quote="解析器把 PDF"), document
    )

    assert warnings == []
    assert knowledge.document_id == document.id
    assert knowledge.document_title == document.title
    assert [entity.name for entity in knowledge.entities] == ["解析器"]
    assert knowledge.entities[0].type == "system"
    assert knowledge.entities[0].aliases == ["Parser"]
    assert knowledge.entities[0].sources[0].section_id == section.id
    assert knowledge.entities[0].sources[0].document_id == document.id
    assert knowledge.entities[0].sources[0].quote == "解析器把 PDF"
    assert knowledge.facts[0].object == "Document"
    assert knowledge.relations[0].source_id == knowledge.entities[0].id
    assert knowledge.relations[0].target_id == knowledge.concepts[0].id


def test_missing_top_level_field_is_rejected(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload()
    payload.pop("facts")

    with pytest.raises(InvalidPayloadError) as error:
        validate_payload(payload, document)

    assert "facts" in str(error.value)


def test_wrong_type_for_top_level_field_is_rejected(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload()
    payload["entities"] = {"name": "not a list"}

    with pytest.raises(InvalidPayloadError) as error:
        validate_payload(payload, document)

    assert "must be a list" in str(error.value)


def test_item_without_a_name_is_rejected(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload()
    payload["entities"][0].pop("name")

    with pytest.raises(InvalidPayloadError) as error:
        validate_payload(payload, document)

    assert "entities[0]" in str(error.value)


def test_empty_payload_is_valid(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    knowledge, warnings = validate_payload(empty_payload(), document)

    assert knowledge.is_empty() is True
    assert warnings == []


def test_missing_sources_warn_but_keep_the_item(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload()
    payload["entities"][0].pop("sources")

    knowledge, warnings = validate_payload(payload, document)

    assert knowledge.entities[0].name == "解析器"
    assert knowledge.entities[0].sources == []
    assert any("no sources" in warning for warning in warnings)


def test_unknown_section_id_is_dropped(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload("not-a-real-section")

    knowledge, warnings = validate_payload(payload, document)

    assert knowledge.entities[0].sources[0].section_id is None
    assert any("unknown section id" in warning for warning in warnings)


def test_page_number_is_taken_from_the_cited_section(chinese_pdf: Path) -> None:
    document = load_document(chinese_pdf)
    second_page = document.sections[1]
    payload = sample_payload(second_page.id, page_number=99)

    knowledge, warnings = validate_payload(payload, document)

    assert knowledge.entities[0].sources[0].page_number == 2
    assert any("does not match section" in warning for warning in warnings)


def test_unknown_relation_endpoint_warns_and_keeps_names(
    text_file: Callable[..., Path],
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload()
    payload["relations"][0]["target"] = "没有提到过的名字"

    knowledge, warnings = validate_payload(payload, document)

    relation = knowledge.relations[0]
    assert relation.target == "没有提到过的名字"
    assert relation.target_id is None
    assert any(
        "does not match any extracted entity" in warning for warning in warnings
    )


def test_duplicate_entities_are_merged(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    section = document.sections[0]
    payload = sample_payload(section.id)
    payload["entities"].append(
        {
            "name": "解析器",
            "type": "system",
            "description": "",
            "aliases": ["parser core"],
            "sources": [source(section.id, quote="第二个引用")],
        }
    )
    payload["relations"] = []

    knowledge, warnings = validate_payload(payload, document)

    assert len(knowledge.entities) == 1
    assert len(knowledge.entities[0].sources) == 2
    assert "parser core" in knowledge.entities[0].aliases
    assert any("duplicate entities" in warning for warning in warnings)


def test_unknown_top_level_field_is_ignored_with_a_warning(
    text_file: Callable[..., Path],
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload(document.sections[0].id)
    payload["summary"] = "the model tried to add a summary"

    knowledge, warnings = validate_payload(payload, document)

    assert knowledge.is_empty() is False
    assert any("unknown top-level field" in warning for warning in warnings)
    assert "summary" not in json.dumps(knowledge.to_dict())
