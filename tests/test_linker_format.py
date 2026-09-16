"""Link formatting tests: paths, escaping, styles."""

from __future__ import annotations

import pytest

from compiler.linker import (
    LINK_STYLE_MARKDOWN,
    LINK_STYLE_WIKI,
    encode_target,
    escape_display,
    format_link,
    relative_target,
)


def test_encode_target_keeps_chinese_readable() -> None:
    assert encode_target("解析器.md") == "解析器.md"


def test_encode_target_escapes_destination_breakers() -> None:
    assert encode_target("my page(1).md") == "my%20page%281%29.md"
    assert encode_target("a[b]c.md") == "a%5Bb%5Dc.md"
    assert encode_target("100%.md") == "100%25.md"


def test_escape_display_only_touches_link_syntax() -> None:
    assert escape_display("解析器") == "解析器"
    assert escape_display("a[b]c") == "a\\[b\\]c"
    assert escape_display("back\\slash") == "back\\\\slash"


def test_relative_target_in_the_same_directory() -> None:
    assert relative_target("index.md", "解析器.md") == "解析器.md"


def test_relative_target_from_a_subdirectory() -> None:
    assert relative_target("sub/page.md", "index.md") == "../index.md"
    assert relative_target("sub/deep/page.md", "a.md") == "../../a.md"


def test_relative_target_always_uses_forward_slashes() -> None:
    assert relative_target("index.md", "sub\\page.md") == "sub/page.md"
    assert "\\" not in relative_target("a\\b.md", "c.md")


def test_format_link_defaults_to_markdown() -> None:
    assert format_link("解析器", "解析器.md") == "[解析器](解析器.md)"
    assert format_link("my page", "my page.md") == "[my page](my%20page.md)"


def test_format_link_uses_relative_paths() -> None:
    assert (
        format_link("解析器", "解析器.md", from_path="sub/index.md")
        == "[解析器](../解析器.md)"
    )


def test_format_link_wiki_style() -> None:
    assert format_link("解析器", "解析器.md", style=LINK_STYLE_WIKI) == "[[解析器]]"


def test_format_link_escapes_the_display_text() -> None:
    assert format_link("a[b]", "a[b].md") == "[a\\[b\\]](a%5Bb%5D.md)"


def test_format_link_rejects_unknown_styles() -> None:
    with pytest.raises(ValueError):
        format_link("x", "x.md", style="html")


def test_markdown_is_the_default_style() -> None:
    assert LINK_STYLE_MARKDOWN == "markdown"
    assert LINK_STYLE_WIKI == "wiki"
