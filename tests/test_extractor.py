"""End to end extraction tests with a mock LLM (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from compiler.document import load_document
from compiler.extraction import (
    PROMPT_VERSION,
    Extractor,
    InvalidPayloadError,
    InvalidResponseError,
    extract_knowledge,
)
from compiler.knowledge import KnowledgeIR
from compiler.llm import LLMError
from support import ScriptedLLMClient, empty_payload, payload_json, sample_payload

MARKDOWN_SAMPLE = (
    "---\n"
    "title: 解析器设计笔记\n"
    "---\n"
    "\n"
    "# 总览\n"
    "\n"
    "解析器把 PDF、Markdown、TXT 统一成 Document。\n"
    "\n"
    "## 编码处理\n"
    "\n"
    "支持 UTF-8、GB18030、Big5。\n"
)


def test_extracts_a_knowledge_ir_with_a_mock_llm(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    client = ScriptedLLMClient(payload_json(document.sections[0].id))

    knowledge = extract_knowledge(document, client)

    assert isinstance(knowledge, KnowledgeIR)
    assert knowledge.document_id == document.id
    assert [entity.name for entity in knowledge.entities] == ["解析器"]
    assert [concept.name for concept in knowledge.concepts] == ["文档模型"]
    assert len(knowledge.facts) == 1
    assert knowledge.relations[0].type == "produces"
    assert len(client.calls) == 1


def test_result_metadata_records_model_prompt_version_and_counts(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    client = ScriptedLLMClient(payload_json(document.sections[0].id))

    knowledge = extract_knowledge(document, client)

    assert knowledge.metadata["model"] == "mock-model"
    assert knowledge.metadata["prompt_version"] == PROMPT_VERSION
    assert knowledge.metadata["warnings"] == []
    assert knowledge.metadata["counts"] == {
        "entities": 1,
        "concepts": 1,
        "facts": 1,
        "relations": 1,
    }


def test_sources_point_back_at_document_and_sections(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    encoding_section = document.sections[0].children[0]
    client = ScriptedLLMClient(payload_json(encoding_section.id))

    knowledge = extract_knowledge(document, client)

    ref = knowledge.entities[0].sources[0]
    assert ref.document_id == document.id
    assert ref.section_id == encoding_section.id
    assert ref.quote == "原文片段"


def test_pdf_pages_end_up_in_the_sources(chinese_pdf: Path) -> None:
    document = load_document(chinese_pdf)
    second_page = document.sections[1]
    client = ScriptedLLMClient(payload_json(second_page.id))

    knowledge = extract_knowledge(document, client)

    assert knowledge.entities[0].sources[0].page_number == 2
    assert knowledge.entities[0].sources[0].section_id == second_page.id


def test_multiple_sections_are_cited_individually(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    sections = list(document.walk_sections())
    client = ScriptedLLMClient(payload_json(sections[1].id))

    knowledge = extract_knowledge(document, client)

    assert knowledge.entities[0].sources[0].section_id == sections[1].id
    assert f"[section {sections[0].id}]" in client.last_user_prompt
    assert f"[section {sections[1].id}]" in client.last_user_prompt


def test_illegal_json_raises_invalid_response_error(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    client = ScriptedLLMClient("Sure! Here is the knowledge: {oops")

    with pytest.raises(InvalidResponseError):
        extract_knowledge(document, client)

    assert len(client.calls) == 1


def test_missing_field_raises_invalid_payload_error(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    payload = sample_payload(document.sections[0].id)
    payload.pop("relations")
    client = ScriptedLLMClient(json.dumps(payload, ensure_ascii=False))

    with pytest.raises(InvalidPayloadError) as error:
        extract_knowledge(document, client)

    assert "relations" in str(error.value)


def test_empty_result_is_a_valid_empty_ir(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    client = ScriptedLLMClient(json.dumps(empty_payload()))

    knowledge = extract_knowledge(document, client)

    assert knowledge.is_empty() is True
    assert knowledge.metadata["counts"] == {
        "entities": 0,
        "concepts": 0,
        "facts": 0,
        "relations": 0,
    }


def test_chinese_document_is_preserved(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("cn.md", MARKDOWN_SAMPLE))
    encoding_section = list(document.walk_sections())[1]
    client = ScriptedLLMClient(
        payload_json(encoding_section.id, quote="支持 UTF-8")
    )

    knowledge = extract_knowledge(document, client)

    assert knowledge.entities[0].name == "解析器"
    assert knowledge.concepts[0].name == "文档模型"
    assert knowledge.facts[0].statement.startswith("解析器把 PDF")
    assert knowledge.entities[0].sources[0].quote == "支持 UTF-8"
    assert "解析器把 PDF" in client.last_user_prompt


def test_fenced_json_answer_is_accepted(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    fenced = "```json\n" + payload_json(document.sections[0].id) + "\n```"
    client = ScriptedLLMClient(fenced)

    knowledge = extract_knowledge(document, client)

    assert knowledge.entities
    assert any(
        "code fence" in warning for warning in knowledge.metadata["warnings"]
    )


def test_llm_errors_propagate(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    client = ScriptedLLMClient(LLMError("rate limited"))

    with pytest.raises(LLMError):
        extract_knowledge(document, client)


def test_extractor_rejects_input_that_is_not_a_document() -> None:
    client = ScriptedLLMClient(payload_json())

    with pytest.raises(TypeError) as error:
        Extractor(client).extract("just a path")  # type: ignore[arg-type]

    assert "Document Model object" in str(error.value)
    assert client.calls == []


def test_output_is_json_friendly_and_not_markdown(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    client = ScriptedLLMClient(payload_json(document.sections[0].id))

    knowledge = extract_knowledge(document, client)
    serialized = json.dumps(knowledge.to_dict(), ensure_ascii=False)
    restored = KnowledgeIR.from_dict(json.loads(serialized))

    assert restored == knowledge
    assert "```" not in serialized
    assert "#" not in knowledge.entities[0].name
