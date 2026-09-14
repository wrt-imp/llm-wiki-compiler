"""Parser registry tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from compiler.parser import (
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    FORMAT_TXT,
    Document,
    MarkdownParser,
    ParserRegistry,
    PdfParser,
    TxtParser,
    create_default_registry,
    parse_file,
)
from compiler.parser.errors import UnsupportedFormatError


@pytest.fixture
def registry() -> ParserRegistry:
    return create_default_registry()


def test_selects_parser_by_extension(registry: ParserRegistry) -> None:
    assert isinstance(registry.get_parser("notes.txt"), TxtParser)
    assert isinstance(registry.get_parser("notes.md"), MarkdownParser)
    assert isinstance(registry.get_parser("notes.markdown"), MarkdownParser)
    assert isinstance(registry.get_parser("paper.pdf"), PdfParser)


def test_extension_matching_is_case_insensitive(registry: ParserRegistry) -> None:
    assert isinstance(registry.get_parser("NOTES.TXT"), TxtParser)
    assert isinstance(registry.get_parser(Path("Paper.PDF")), PdfParser)


def test_supported_extensions_are_reported(registry: ParserRegistry) -> None:
    assert registry.supported_extensions == (".markdown", ".md", ".pdf", ".txt")


def test_unsupported_format_raises_clear_error(registry: ParserRegistry) -> None:
    with pytest.raises(UnsupportedFormatError) as error:
        registry.get_parser("data.csv")

    message = str(error.value)
    assert ".csv" in message
    assert ".pdf" in message and ".txt" in message and ".md" in message


def test_file_without_extension_raises_clear_error(registry: ParserRegistry) -> None:
    with pytest.raises(UnsupportedFormatError) as error:
        registry.get_parser("README")

    assert "no file extension" in str(error.value)


def test_unsupported_format_error_is_a_parser_error() -> None:
    from compiler.parser.errors import ParserError

    assert issubclass(UnsupportedFormatError, ParserError)


def test_parse_dispatches_by_extension(
    registry: ParserRegistry, text_file: Callable[..., Path]
) -> None:
    txt = text_file("a.txt", "txt body\n")
    md = text_file("b.md", "# Markdown body\n")

    assert registry.parse(txt).format == FORMAT_TXT
    assert registry.parse(md).format == FORMAT_MARKDOWN


def test_parse_file_uses_the_default_registry(text_file: Callable[..., Path]) -> None:
    path = text_file("default.txt", "default registry\n")

    document = parse_file(path)

    assert document.format == FORMAT_TXT
    assert document.content == "default registry\n"


def test_parse_all_returns_documents_in_order(
    registry: ParserRegistry, text_file: Callable[..., Path]
) -> None:
    first = text_file("first.txt", "one\n")
    second = text_file("second.md", "# two\n")

    documents = registry.parse_all([first, second])

    assert [document.format for document in documents] == [
        FORMAT_TXT,
        FORMAT_MARKDOWN,
    ]


def test_parse_unsupported_format_through_registry(
    registry: ParserRegistry, text_file: Callable[..., Path]
) -> None:
    with pytest.raises(UnsupportedFormatError):
        registry.parse(text_file("data.csv", "a,b\n"))


def test_new_parser_can_be_registered(text_file: Callable[..., Path]) -> None:
    class UpperParser(TxtParser):
        """Minimal custom parser used to check that registration is cheap."""

        format = "upper"
        extensions = (".upper",)

        def parse(self, path: Any) -> Document:
            document = super().parse(path)
            document.metadata: Dict[str, Any] = dict(document.metadata)
            document.content = document.content.upper()
            return document

    registry = ParserRegistry([TxtParser(), UpperParser()])
    path = text_file("shout.upper", "quiet\n")

    document = registry.parse(path)

    assert document.format == "upper"
    assert document.content == "QUIET\n"


def test_pdf_extension_is_routed_to_the_pdf_parser(
    registry: ParserRegistry, sample_pdf: Path
) -> None:
    document = registry.parse(sample_pdf)

    assert document.format == FORMAT_PDF
    assert document.metadata["page_count"] == 2
