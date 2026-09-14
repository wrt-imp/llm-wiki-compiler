"""PDF parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.parser import FORMAT_PDF, PdfParser
from compiler.parser.errors import ParserError


def test_parses_pdf_and_keeps_page_information(sample_pdf: Path) -> None:
    document = PdfParser().parse(sample_pdf)

    assert document.format == FORMAT_PDF
    assert document.metadata["page_count"] == 2
    assert [page["page_number"] for page in document.metadata["pages"]] == [1, 2]
    assert "Page one" in document.metadata["pages"][0]["text"]
    assert "P2" in document.metadata["pages"][1]["text"]

    # content is the page texts joined in reading order
    assert "Page one" in document.content
    assert "P2" in document.content


def test_uses_pdf_document_information_for_title(sample_pdf: Path) -> None:
    document = PdfParser().parse(sample_pdf)

    assert document.title == "Parser Design Notes"
    assert document.metadata["pdf_metadata"]["title"] == "Parser Design Notes"
    assert document.metadata["pdf_metadata"]["author"] == "Wiki Compiler Team"
    assert document.metadata["encrypted"] is False
    assert document.metadata["empty_pages"] == []


def test_parses_chinese_pdf(chinese_pdf: Path) -> None:
    document = PdfParser().parse(chinese_pdf)

    assert document.metadata["page_count"] == 2
    assert "知识图谱编译器" in document.metadata["pages"][0]["text"]
    assert "来源追踪" in document.metadata["pages"][1]["text"]
    assert "知识图谱编译器" in document.content
    # No document information in that fixture, so the first page line wins.
    assert document.title == "知识图谱编译器：解析器阶段"


def test_missing_pdf_raises_source_not_found(tmp_path: Path) -> None:
    from compiler.parser.errors import SourceNotFoundError

    with pytest.raises(SourceNotFoundError):
        PdfParser().parse(tmp_path / "missing.pdf")


def test_corrupt_pdf_raises_parser_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf file")

    with pytest.raises(ParserError) as error:
        PdfParser().parse(broken)

    assert "broken.pdf" in str(error.value)
