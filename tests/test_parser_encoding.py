"""Encoding detection tests (UTF-8 / GBK / Big5 / BOMs)."""

from __future__ import annotations

import codecs
from typing import Any

import pytest

from compiler.parser.encoding import (
    CANDIDATE_ENCODINGS,
    DecodedText,
    decode_bytes,
    normalize_newlines,
)
from compiler.parser import encoding as encoding_module

SHORT_GBK = "Parser 把源文件转换成文档模型。\n"
LONG_GBK = "知识图谱编译器\n" * 20 + "解析器把 PDF、Markdown、TXT 统一成 Document。\n"


def test_short_gbk_text_is_decoded_correctly() -> None:
    """Regression: a small GBK file used to be detected as cp949."""

    decoded = decode_bytes(SHORT_GBK.encode("gbk"))

    assert decoded.text == SHORT_GBK
    assert decoded.encoding in {"gbk", "gb18030"}
    assert decoded.had_errors is False


def test_longer_gbk_text_is_decoded_correctly() -> None:
    data = LONG_GBK.encode("gbk")

    decoded = decode_bytes(data)

    assert decoded.text == LONG_GBK
    assert decoded.encoding in {"gbk", "gb18030"}


def test_utf8_is_preferred_when_valid() -> None:
    decoded = decode_bytes("解析器\n".encode("utf-8"))

    assert decoded.encoding == "utf-8"
    assert decoded.text == "解析器\n"


def test_utf8_bom_is_stripped() -> None:
    decoded = decode_bytes(codecs.BOM_UTF8 + "解析器".encode("utf-8"))

    assert decoded.encoding == "utf-8-sig"
    assert decoded.text == "解析器"


def test_utf16_bom_is_recognised() -> None:
    decoded = decode_bytes("解析器".encode("utf-16"))

    assert decoded.encoding == "utf-16"
    assert decoded.text == "解析器"


def test_ascii_text_stays_utf8() -> None:
    decoded = decode_bytes(b"graph TD\n")

    assert decoded.encoding == "utf-8"
    assert decoded.text == "graph TD\n"


def test_explicit_encoding_wins() -> None:
    decoded = decode_bytes(SHORT_GBK.encode("gb18030"), encoding="gb18030")

    assert decoded.encoding == "gb18030"
    assert decoded.text == SHORT_GBK


def test_big5_is_handled_by_the_detector() -> None:
    text = "知識圖譜編譯器與解析器\n"
    try:
        data = text.encode("big5")
    except UnicodeEncodeError:  # pragma: no cover - codepage dependent
        pytest.skip("big5 cannot encode this sample")

    decoded = decode_bytes(data)

    assert decoded.text == text
    assert decoded.encoding in {"big5", "big5hkscs"}


def test_chinese_candidates_are_preferred() -> None:
    assert CANDIDATE_ENCODINGS == ("gb18030", "big5")


def test_undecodable_bytes_are_flagged_not_raised(
    monkeypatch: "Any",
) -> None:
    # without the detector the strict attempts decide; 0xff is invalid in
    # UTF-8, GB18030 and Big5 alike
    monkeypatch.setattr(encoding_module, "_detect_from_bytes", None)

    decoded = decode_bytes(b"\xff\xff")

    assert isinstance(decoded, DecodedText)
    assert decoded.had_errors is True
    assert decoded.encoding == "utf-8"


def test_newlines_are_normalized() -> None:
    decoded = decode_bytes("a\r\nb\rc\n".encode("utf-8"))

    assert decoded.text == "a\nb\nc\n"
    assert normalize_newlines("a\r\nb") == "a\nb"
