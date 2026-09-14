"""Extraction prompt tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from compiler.document import Document, load_document
from compiler.extraction import (
    SYSTEM_PROMPT,
    build_extraction_prompt,
    build_user_prompt,
)

MARKDOWN_SAMPLE = (
    "# 总览\n\n解析器把 PDF、Markdown、TXT 统一成 Document。\n"
    "\n## 编码处理\n\n支持 UTF-8、GB18030、Big5。\n"
)


def test_system_prompt_states_the_extraction_rules() -> None:
    for expected in (
        "JSON object",
        "Never add outside knowledge",
        "No markdown",
        '"sources"',
        "section_id",
        "entity",
        "concept",
        "fact",
        "relation",
        "return the four arrays empty",
        "Do not translate",
    ):
        assert expected in SYSTEM_PROMPT


def test_build_returns_system_and_user_prompt(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    system_prompt, user_prompt = build_extraction_prompt(document)

    assert system_prompt == SYSTEM_PROMPT
    assert "Sections" in user_prompt


def test_user_prompt_includes_document_identity(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    prompt = build_user_prompt(document)

    assert f"id: {document.id}" in prompt
    assert f"title: {document.title}" in prompt
    assert f"source: {document.source}" in prompt
    assert f"format: {document.format}" in prompt


def test_user_prompt_labels_every_section_in_order(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    prompt = build_user_prompt(document)
    positions = [
        prompt.index(f"[section {section.id}]") for section in document.walk_sections()
    ]

    assert positions == sorted(positions)
    assert "编码处理" in prompt


def test_user_prompt_keeps_chinese_text(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("cn.md", MARKDOWN_SAMPLE))

    prompt = build_user_prompt(document)

    assert "解析器把 PDF、Markdown、TXT 统一成 Document。" in prompt
    assert "支持 UTF-8、GB18030、Big5。" in prompt


def test_user_prompt_marks_pdf_pages(sample_pdf: Path) -> None:
    document = load_document(sample_pdf)

    prompt = build_user_prompt(document)

    for section in document.walk_sections():
        page = section.metadata["page_number"]
        assert f"[section {section.id} | page {page}]" in prompt
    assert "Page one" in prompt


def test_document_without_sections_still_produces_a_prompt() -> None:
    document = Document(
        id="doc",
        title="hand made",
        source="notes.txt",
        format="txt",
        content="只有正文，没有 sections。",
    )

    prompt = build_user_prompt(document)

    assert '"section_id": null' in prompt
    assert "只有正文，没有 sections。" in prompt
