"""Document Model builder tests: Parser output -> sections."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pytest

from compiler.document import (
    SECTION_KIND_DOCUMENT,
    SECTION_KIND_HEADING,
    SECTION_KIND_PAGE,
    SECTION_KIND_PREAMBLE,
    Document,
    Section,
    attach_sections,
    build_sections,
    load_document,
)
from compiler.parser import parse_file
from compiler.parser.errors import UnsupportedFormatError

MARKDOWN_SAMPLE = (
    "---\n"
    "title: 解析器设计笔记\n"
    "tags: [wiki, parser]\n"
    "---\n"
    "\n"
    "写在第一个标题之前的前言段落。\n"
    "\n"
    "# 总览\n"
    "\n"
    "解析器把 PDF、Markdown、TXT 统一成 Document。\n"
    "\n"
    "## 编码处理\n"
    "\n"
    "支持 UTF-8、GB18030、Big5。\n"
    "\n"
    "```python\n"
    "# 这不是标题\n"
    "```\n"
    "\n"
    "## 页面信息\n"
    "\n"
    "PDF 保留每页文本。\n"
    "\n"
    "### 子章节示例\n"
    "\n"
    "更深一层的内容。\n"
)


def find_by_title(sections: list[Section], title: str) -> Optional[Section]:
    for section in sections:
        for candidate in section.walk():
            if candidate.title == title:
                return candidate
    return None


# ----------------------------------------------------------------------
# TXT
# ----------------------------------------------------------------------
def test_txt_becomes_one_section(text_file: Callable[..., Path]) -> None:
    path = text_file("manual.txt", "中文说明书\n\n第一段：解析器只做一件事。\n")

    document = load_document(path)

    assert len(document.sections) == 1
    section = document.sections[0]
    assert section.id == f"{document.id}#1"
    assert section.title == document.title == "中文说明书"
    assert section.content == document.content
    assert section.level == 1
    assert section.children == []
    assert section.metadata == {
        "kind": SECTION_KIND_DOCUMENT,
        "line_start": 1,
        "line_end": 3,
    }


# ----------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------
def test_markdown_builds_the_heading_tree(text_file: Callable[..., Path]) -> None:
    path = text_file("design.md", MARKDOWN_SAMPLE)

    document = load_document(path)

    assert [section.title for section in document.sections] == ["", "总览"]

    overview = document.sections[1]
    assert overview.level == 1
    assert overview.metadata["heading_level"] == 1
    assert [child.title for child in overview.children] == ["编码处理", "页面信息"]

    encoding = overview.children[0]
    assert encoding.level == 2
    assert encoding.metadata["heading_level"] == 2
    assert encoding.children == []

    pages = overview.children[1]
    assert pages.level == 2
    assert [child.title for child in pages.children] == ["子章节示例"]
    assert pages.children[0].level == 3
    assert pages.children[0].metadata["heading_level"] == 3


def test_markdown_section_ids_are_ordinal_paths(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    assert [section.id for section in document.walk_sections()] == [
        f"{document.id}#1",
        f"{document.id}#2",
        f"{document.id}#2.1",
        f"{document.id}#2.2",
        f"{document.id}#2.2.1",
    ]


def test_markdown_preamble_section(text_file: Callable[..., Path]) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    preamble = document.sections[0]

    assert preamble.title == ""
    assert preamble.content == "写在第一个标题之前的前言段落。"
    assert preamble.metadata == {
        "kind": SECTION_KIND_PREAMBLE,
        "line_start": 1,
        "line_end": 2,
    }


def test_markdown_headings_are_not_taken_from_code_fences(
    text_file: Callable[..., Path],
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))

    titles = [section.title for section in document.walk_sections()]

    assert "这不是标题" not in titles
    # the fence belongs to the section it sits in
    assert "```python" in find_by_title(document.sections, "编码处理").content


def test_markdown_section_content_excludes_nested_sections(
    text_file: Callable[..., Path],
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    overview = document.sections[1]

    assert overview.content == "解析器把 PDF、Markdown、TXT 统一成 Document。"
    assert "支持 UTF-8" not in overview.content
    assert "更深一层的内容。" not in overview.content


def test_markdown_sections_cover_the_whole_content(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    regions = [
        (section.metadata["line_start"], section.metadata["line_end"])
        for section in document.walk_sections()
    ]

    # regions are contiguous and in document order
    assert regions[0][0] == 1
    for (_, previous_end), (next_start, _) in zip(regions, regions[1:]):
        assert previous_end + 1 == next_start
    assert regions[-1][1] == len(document.content.splitlines())


def test_markdown_section_titles_match_parser_headings(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    heading_sections = [
        section
        for section in document.walk_sections()
        if section.metadata["kind"] == SECTION_KIND_HEADING
    ]

    assert [section.title for section in heading_sections] == [
        heading["text"] for heading in document.metadata["headings"]
    ]
    assert [section.metadata["heading_level"] for section in heading_sections] == [
        heading["level"] for heading in document.metadata["headings"]
    ]


def test_markdown_level_jumps_keep_file_hierarchy(
    text_file: Callable[..., Path]
) -> None:
    path = text_file("jumps.md", "## 二级开头\n\n内容\n\n#### 跳到四级\n\n更深内容\n")

    document = load_document(path)

    assert [section.title for section in document.sections] == ["二级开头"]
    top = document.sections[0]
    assert top.level == 1  # tree depth, not the markdown level
    assert top.metadata["heading_level"] == 2
    assert [child.title for child in top.children] == ["跳到四级"]
    assert top.children[0].level == 2
    assert top.children[0].metadata["heading_level"] == 4


def test_markdown_without_headings_is_one_section(
    text_file: Callable[..., Path]
) -> None:
    document = load_document(text_file("plain.md", "只有正文，没有标题。\n"))

    assert len(document.sections) == 1
    assert document.sections[0].metadata["kind"] == SECTION_KIND_DOCUMENT
    assert document.sections[0].content == document.content


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------
def test_pdf_pages_become_sections(sample_pdf: Path) -> None:
    document = load_document(sample_pdf)

    assert [section.title for section in document.sections] == ["Page 1", "Page 2"]
    assert [section.metadata["kind"] for section in document.sections] == [
        SECTION_KIND_PAGE,
        SECTION_KIND_PAGE,
    ]
    assert [section.metadata["page_number"] for section in document.sections] == [1, 2]
    assert [section.level for section in document.sections] == [1, 1]
    assert "Page one" in document.sections[0].content
    assert "P2" in document.sections[1].content


def test_pdf_page_sections_cover_the_document_content(
    sample_pdf: Path, chinese_pdf: Path
) -> None:
    for path in (sample_pdf, chinese_pdf):
        document = load_document(path)

        joined = "\n\n".join(section.content for section in document.sections)

        assert joined == document.content
        assert len(document.sections) == document.metadata["page_count"]


def test_pdf_keeps_empty_pages() -> None:
    parsed = Document(
        id="abc",
        title="scanned",
        source="scanned.pdf",
        format="pdf",
        content="page one\n\npage three",
        metadata={
            "page_count": 3,
            "pages": [
                {"page_number": 1, "text": "page one"},
                {"page_number": 2, "text": ""},
                {"page_number": 3, "text": "page three"},
            ],
        },
    )

    sections = build_sections(parsed)

    assert [section.metadata["page_number"] for section in sections] == [1, 2, 3]
    assert sections[1].content == ""
    assert sections[1].title == "Page 2"


def test_pdf_without_page_metadata_falls_back_to_one_section() -> None:
    parsed = Document(
        id="abc",
        title="odd",
        source="odd.pdf",
        format="pdf",
        content="all the text",
        metadata={},
    )

    sections = build_sections(parsed)

    assert len(sections) == 1
    assert sections[0].metadata["kind"] == SECTION_KIND_DOCUMENT


# ----------------------------------------------------------------------
# Chinese sources, metadata and end to end behaviour
# ----------------------------------------------------------------------
def test_chinese_documents_keep_their_text(
    text_file: Callable[..., Path], chinese_pdf: Path
) -> None:
    markdown = load_document(text_file("cn.md", "# 知识图谱编译器\n\n中文正文内容。\n"))
    pdf = load_document(chinese_pdf)

    assert markdown.sections[0].title == "知识图谱编译器"
    assert markdown.sections[0].content == "中文正文内容。"
    assert pdf.sections[0].content == "知识图谱编译器：解析器阶段"
    assert pdf.sections[1].content == "第二页：保留页面信息，便于来源追踪。"


def test_metadata_is_passed_through(
    text_file: Callable[..., Path], sample_pdf: Path
) -> None:
    markdown = load_document(text_file("design.md", MARKDOWN_SAMPLE))
    pdf = load_document(sample_pdf)

    assert markdown.metadata["encoding"] == "utf-8"
    assert markdown.metadata["front_matter"] == {
        "title": "解析器设计笔记",
        "tags": ["wiki", "parser"],
    }
    assert pdf.metadata["page_count"] == 2
    assert pdf.metadata["pages"][1]["text"]
    assert pdf.metadata["pdf_metadata"]["title"] == "Parser Design Notes"


def test_attach_sections_leaves_the_parser_output_untouched(
    text_file: Callable[..., Path]
) -> None:
    parsed = parse_file(text_file("design.md", MARKDOWN_SAMPLE))

    structured = attach_sections(parsed)

    assert parsed.sections == []
    assert structured.sections
    assert structured.content == parsed.content
    assert structured.title == parsed.title
    assert structured.id == parsed.id


def test_unknown_format_falls_back_to_one_section() -> None:
    parsed = Document(
        id="abc",
        title="legacy",
        source="legacy.rst",
        format="rst",
        content="body",
        metadata={},
    )

    sections = build_sections(parsed)

    assert len(sections) == 1
    assert sections[0] == Section(
        id="abc#1",
        title="legacy",
        content="body",
        level=1,
        metadata={"kind": SECTION_KIND_DOCUMENT, "line_start": 1, "line_end": 1},
    )


def test_load_document_reports_unsupported_formats(
    text_file: Callable[..., Path]
) -> None:
    with pytest.raises(UnsupportedFormatError):
        load_document(text_file("data.csv", "a,b\n"))
