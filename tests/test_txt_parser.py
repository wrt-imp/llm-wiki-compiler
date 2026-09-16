"""TXT parser tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from compiler.parser import FORMAT_TXT, Document, TxtParser
from compiler.parser.errors import SourceNotFoundError


def test_parses_plain_txt(text_file: Callable[..., Path]) -> None:
    path = text_file("notes.txt", "Compiler design notes\n\nsecond paragraph\n")

    document = TxtParser().parse(path)

    assert isinstance(document, Document)
    assert document.format == FORMAT_TXT
    assert document.content == "Compiler design notes\n\nsecond paragraph\n"
    assert document.title == "Compiler design notes"
    assert document.source == str(path)
    assert document.metadata["encoding"] == "utf-8"
    assert document.metadata["line_count"] == 3
    assert document.metadata["char_count"] == len(document.content)
    assert document.metadata["had_decoding_errors"] is False


def test_parses_utf8_chinese_txt(text_file: Callable[..., Path]) -> None:
    text = "知识图谱编译器\n\n解析器阶段：PDF、Markdown、TXT。\n"
    path = text_file("chinese.txt", text, encoding="utf-8")

    document = TxtParser().parse(path)

    assert document.content == text
    assert document.title == "知识图谱编译器"
    assert document.metadata["encoding"] == "utf-8"
    assert "解析器阶段" in document.content


def test_parses_gbk_chinese_txt(text_file: Callable[..., Path]) -> None:
    text = "知识图谱编译器\n\n解析器阶段：中文编码测试。\n"
    path = text_file("gbk.txt", text, encoding="gbk")

    document = TxtParser().parse(path)

    assert document.content == text
    assert document.title == "知识图谱编译器"
    assert document.metadata["encoding"] in {"gbk", "gb18030"}
    assert document.metadata["had_decoding_errors"] is False


def test_parses_short_gbk_txt(text_file: Callable[..., Path]) -> None:
    """Regression: short GBK files used to be decoded as cp949."""

    text = "Parser 把源文件转换成文档模型。\n"
    path = text_file("short_gbk.txt", text, encoding="gbk")

    document = TxtParser().parse(path)

    assert document.content == text
    assert document.metadata["encoding"] in {"gbk", "gb18030"}


def test_parses_utf8_bom_txt(text_file: Callable[..., Path]) -> None:
    path = text_file("bom.txt", "带 BOM 的文本\n", encoding="utf-8-sig")

    document = TxtParser().parse(path)

    # The BOM must not leak into the content or the title.
    assert document.content == "带 BOM 的文本\n"
    assert document.title == "带 BOM 的文本"
    assert document.metadata["encoding"] == "utf-8-sig"


def test_normalizes_crlf_line_endings(text_file: Callable[..., Path]) -> None:
    path = text_file("crlf.txt", "line one\r\nline two\r\n")

    document = TxtParser().parse(path)

    assert document.content == "line one\nline two\n"


def test_first_visible_line_becomes_the_title(text_file: Callable[..., Path]) -> None:
    path = text_file("leading_blanks.txt", "\n\n   \nReal title line\nbody\n")

    document = TxtParser().parse(path)

    assert document.title == "Real title line"


def test_title_falls_back_to_file_name(text_file: Callable[..., Path]) -> None:
    path = text_file("empty_source.txt", "\n   \n")

    document = TxtParser().parse(path)

    assert document.title == "empty_source"


def test_missing_file_raises_source_not_found(tmp_path: Path) -> None:
    with pytest.raises(SourceNotFoundError):
        TxtParser().parse(tmp_path / "does_not_exist.txt")


def test_directory_raises_source_not_found(tmp_path: Path) -> None:
    with pytest.raises(SourceNotFoundError):
        TxtParser().parse(tmp_path)
