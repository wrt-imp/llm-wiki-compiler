"""Protected region tests: what the resolver must never touch."""

from __future__ import annotations

from compiler.linker import protected_spans

FRONT_MATTER = '---\nid: "abc"\nkind: "entity"\npage: "解析器.md"\n---\n# 解析器\n'


def is_protected(text: str, needle: str, **kwargs) -> bool:
    spans = protected_spans(text, **kwargs)
    start = text.index(needle)
    end = start + len(needle)
    return any(span_start <= start and end <= span_end for span_start, span_end in spans)


def test_front_matter_is_protected() -> None:
    assert is_protected(FRONT_MATTER, 'page: "解析器.md"')
    assert is_protected(FRONT_MATTER, "kind:")


def test_heading_line_is_protected() -> None:
    text = "# 解析器\n\n解析器是组件。\n"

    assert is_protected(text, "# 解析器")
    assert not is_protected(text, "解析器是组件")


def test_fenced_code_block_is_protected() -> None:
    text = "正文 解析器\n\n```python\nprint('解析器')\n```\n\n结尾 解析器\n"

    assert is_protected(text, "```python")
    assert is_protected(text, "print('解析器')")
    assert not is_protected(text, "正文 解析器")
    assert not is_protected(text, "结尾 解析器")


def test_tilde_fence_is_protected() -> None:
    text = "~~~\n解析器\n~~~\n解析器\n"

    assert is_protected(text, "~~~\n解析器\n~~~")


def test_inline_code_is_protected() -> None:
    text = "文档 `解析器.md` 与 解析器\n"

    assert is_protected(text, "`解析器.md`")
    assert not is_protected(text, "与 解析器")


def test_existing_markdown_link_is_protected() -> None:
    text = "- [解析器](解析器.md) 和 解析器\n"

    assert is_protected(text, "[解析器](解析器.md)")


def test_existing_wiki_link_is_protected() -> None:
    text = "[[解析器]] 和 解析器\n"

    assert is_protected(text, "[[解析器]]")


def test_reference_link_and_definition_are_protected() -> None:
    text = "见 [解析器][ref]\n\n[ref]: 解析器.md\n"

    assert is_protected(text, "[解析器][ref]")
    assert is_protected(text, "[ref]: 解析器.md")


def test_autolink_is_protected() -> None:
    text = "<https://example.com/解析器> 和 解析器\n"

    assert is_protected(text, "<https://example.com/解析器>")


def test_sources_section_is_protected_by_default() -> None:
    text = (
        "## Facts\n\n"
        "- 解析器输出文档模型\n\n"
        "## Sources\n\n"
        "1. **docA** — “解析器输出文档模型”\n"
    )

    assert is_protected(text, "“解析器输出文档模型”")
    assert not is_protected(text, "- 解析器输出文档模型")


def test_sources_section_can_be_included() -> None:
    text = "## Sources\n\n1. **docA** — “解析器输出文档模型”\n"

    assert not is_protected(text, "“解析器输出文档模型”", skip_sources_section=False)


def test_spans_are_sorted_and_merged() -> None:
    spans = protected_spans(FRONT_MATTER)

    assert spans == sorted(spans)
    for (_, end), (next_start, _) in zip(spans, spans[1:]):
        assert end <= next_start
