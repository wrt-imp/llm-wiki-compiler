"""Markdown parser tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from compiler.parser import FORMAT_MARKDOWN, MarkdownParser


def test_parses_markdown_with_front_matter(text_file: Callable[..., Path]) -> None:
    text = (
        "---\n"
        "title: Parser Design\n"
        "author: Wiki Compiler Team\n"
        "---\n"
        "\n"
        "# Overview\n"
        "\n"
        "Body text about parsing.\n"
        "\n"
        "## Details\n"
        "\n"
        "More details.\n"
    )
    path = text_file("design.md", text)

    document = MarkdownParser().parse(path)

    assert document.format == FORMAT_MARKDOWN
    assert document.title == "Parser Design"
    assert document.source == str(path)
    assert document.metadata["front_matter"] == {
        "title": "Parser Design",
        "author": "Wiki Compiler Team",
    }
    assert document.metadata["headings"] == [
        {"level": 1, "text": "Overview"},
        {"level": 2, "text": "Details"},
    ]
    # Front matter is metadata, not body content.
    assert not document.content.startswith("---")
    assert document.content.startswith("# Overview")
    assert "title: Parser Design" not in document.content
    assert "Body text about parsing." in document.content


def test_front_matter_lists_and_dates_are_json_friendly(
    text_file: Callable[..., Path],
) -> None:
    pytest.importorskip("yaml")
    text = "---\ntitle: Tagged\ntags:\n  - wiki\n  - parser\ncreated: 2026-09-14\n---\n\nbody\n"
    path = text_file("tagged.md", text)

    document = MarkdownParser().parse(path)

    assert document.metadata["front_matter"]["tags"] == ["wiki", "parser"]
    assert document.metadata["front_matter"]["created"] == "2026-09-14"


def test_titles_falls_back_to_first_heading(text_file: Callable[..., Path]) -> None:
    path = text_file("no_front_matter.md", "intro\n\n# Heading Title\n\nbody\n")

    document = MarkdownParser().parse(path)

    assert document.title == "Heading Title"
    assert document.metadata["front_matter"] == {}


def test_title_falls_back_to_file_name(text_file: Callable[..., Path]) -> None:
    path = text_file("plain_notes.md", "just a paragraph, no headings\n")

    document = MarkdownParser().parse(path)

    assert document.title == "plain_notes"


def test_headings_inside_code_fences_are_ignored(
    text_file: Callable[..., Path],
) -> None:
    text = "# Real\n\n```\n# not a heading\n```\n\n## Also Real\n"
    path = text_file("fenced.md", text)

    document = MarkdownParser().parse(path)

    assert document.metadata["headings"] == [
        {"level": 1, "text": "Real"},
        {"level": 2, "text": "Also Real"},
    ]


def test_supports_markdown_extension(text_file: Callable[..., Path]) -> None:
    path = text_file("note.markdown", "# Ext\n")
    parser = MarkdownParser()

    assert parser.supports(path) is True
    assert parser.supports(text_file("note.txt", "x")) is False
    assert parser.parse(path).format == FORMAT_MARKDOWN
