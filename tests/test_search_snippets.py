"""Snippet tests."""

from __future__ import annotations

from pathlib import Path

from compiler.linker import resolve_wiki
from compiler.search import index_wiki, make_snippet, search
from support import build_sample_wiki, write_wiki_page


def sample_index(tmp_path: Path):
    build = build_sample_wiki(tmp_path)
    resolve_wiki(build)
    return index_wiki(tmp_path / "wiki")


def test_snippet_contains_the_keyword(tmp_path: Path) -> None:
    result = search(sample_index(tmp_path), "统一成")[0]

    assert "统一成" in result.snippet
    assert "\n" not in result.snippet


def test_snippet_hides_link_targets(tmp_path: Path) -> None:
    result = search(sample_index(tmp_path), "知识图谱编译器使用解析器")[0]

    assert "知识图谱编译器使用解析器" in result.snippet
    assert "](" not in result.snippet


def test_snippet_is_clipped_with_ellipses(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    body = "开头" * 100 + "关键字" + "结尾" * 100
    write_wiki_page(root, "long.md", f"# 长页面\n\n{body}\n")

    snippet = search(index_wiki(root), "关键字")[0].snippet

    assert snippet.startswith("…")
    assert snippet.endswith("…")
    assert "关键字" in snippet
    assert len(snippet) < len(body)


def test_snippet_window_is_configurable(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    narrow = search(index, "统一成", snippet_window=5)[0].snippet
    wide = search(index, "统一成", snippet_window=80)[0].snippet

    assert len(narrow) < len(wide)
    assert "统一成" in narrow


def test_snippet_uses_the_earliest_keyword(tmp_path: Path) -> None:
    page = index_wiki(
        _wiki_with(tmp_path, "earliest.md", "# 页面\n\n解析器 先出现，文档模型 后出现\n")
    ).page("earliest.md")

    snippet = make_snippet(page, ["文档模型", "解析器"])

    assert snippet.index("解析器") < snippet.index("文档模型")


def test_snippet_falls_back_to_the_page_head(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(
        root,
        "alias-only.md",
        '---\nid: "x"\nkind: "entity"\naliases:\n  - "Parser"\n---\n'
        "# 解析器\n\n把源文件统一成 Document 的组件\n",
    )
    index = index_wiki(root)

    result = search(index, "Parser")[0]

    assert result.matched_in == ("alias",)
    assert result.snippet.startswith("解析器")
    assert "把源文件统一成 Document 的组件" in result.snippet


def test_snippet_offsets_survive_width_normalization(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(
        root, "width.md", "# 宽字符\n\n说明：ＰＡＲＳＥＲ 是组件\n"
    )

    snippet = search(index_wiki(root), "parser")[0].snippet

    assert "ＰＡＲＳＥＲ" in snippet
    assert "说明：" in snippet


def test_snippet_of_an_empty_body(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "empty.md", '---\nid: "x"\nkind: "entity"\n---\n')

    page = index_wiki(root).page("empty.md")

    assert make_snippet(page, ["anything"]) == ""


def _wiki_with(tmp_path: Path, name: str, text: str) -> Path:
    root = tmp_path / "wiki"
    write_wiki_page(root, name, text)
    return root
