"""Wiki indexing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.linker import resolve_wiki
from compiler.search import (
    KIND_CONCEPT,
    KIND_ENTITY,
    KIND_INDEX,
    KIND_PAGE,
    SearchError,
    display_text,
    extract_title,
    index_wiki,
)
from support import build_sample_wiki, write_wiki_page


def sample_wiki(tmp_path: Path) -> Path:
    build = build_sample_wiki(tmp_path)
    resolve_wiki(build)
    return tmp_path / "wiki"


def test_indexes_markdown_pages_in_a_stable_order(tmp_path: Path) -> None:
    index = index_wiki(sample_wiki(tmp_path))

    assert [page.path for page in index.pages] == [
        "index.md",
        "文档模型.md",
        "知识图谱编译器.md",
        "解析器.md",
    ]
    assert index.metadata["pages_indexed"] == 4


def test_front_matter_fields_are_indexed(tmp_path: Path) -> None:
    index = index_wiki(sample_wiki(tmp_path))
    page = index.page("解析器.md")

    assert page.title == "解析器"
    assert page.kind == KIND_ENTITY
    assert page.object_id == "a7755ec09b9f5bed"
    assert page.aliases == ("Parser",)
    assert page.front_matter["type"] == "system"
    assert page.normalized_title == "解析器"
    assert page.normalized_aliases == ("parser",)


def test_concept_pages_are_indexed(tmp_path: Path) -> None:
    page = index_wiki(sample_wiki(tmp_path)).page("文档模型.md")

    assert page.kind == KIND_CONCEPT
    assert page.aliases == ("Document Model",)


def test_index_page_has_its_own_kind(tmp_path: Path) -> None:
    index = index_wiki(sample_wiki(tmp_path))
    page = index.page("index.md")

    assert page.kind == KIND_INDEX
    assert page.title == "Knowledge Wiki"
    assert page.object_id == ""
    assert page.aliases == ()


def test_page_without_front_matter_is_kind_page(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "hand.md", "# 手写页面\n\n正文\n")

    page = index_wiki(root).page("hand.md")

    assert page.kind == KIND_PAGE
    assert page.title == "手写页面"
    assert page.front_matter == {}


def test_title_falls_back_to_the_file_name(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "no-heading.md", "只有正文\n")

    assert index_wiki(root).page("no-heading.md").title == "no-heading"


def test_front_matter_is_not_searchable_text(tmp_path: Path) -> None:
    page = index_wiki(sample_wiki(tmp_path)).page("解析器.md")

    assert "a7755ec09b9f5bed" not in page.text
    assert "a7755ec09b9f5bed" not in page.display_text
    assert "kind" not in page.display_text
    assert "把源文件统一成 Document 的组件" in page.display_text


def test_display_text_removes_link_targets_and_markers(tmp_path: Path) -> None:
    page = index_wiki(sample_wiki(tmp_path)).page("解析器.md")

    assert "](知识图谱编译器.md)" not in page.display_text
    assert "[知识图谱编译器](知识图谱编译器.md)" not in page.display_text
    assert "知识图谱编译器使用解析器" in page.display_text
    assert "## Facts" not in page.display_text


def test_non_markdown_files_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "page.md", "# Page\n\nbody\n")
    write_wiki_page(root, "notes.txt", "not markdown")
    write_wiki_page(root, "paper.pdf", "%PDF-1.4")

    index = index_wiki(root)

    assert [page.path for page in index.pages] == ["page.md"]
    assert index.metadata["skipped_files"] == ["notes.txt", "paper.pdf"]
    assert index.metadata["files_scanned"] == 3


def test_empty_directory_is_not_an_error(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    root.mkdir()

    index = index_wiki(root)

    assert index.pages == []
    assert index.metadata["pages_indexed"] == 0


def test_missing_directory_raises_search_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope"

    with pytest.raises(SearchError) as error:
        index_wiki(missing)

    assert str(missing) in str(error.value)


def test_path_that_is_a_file_raises_search_error(tmp_path: Path) -> None:
    blocker = tmp_path / "wiki"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SearchError) as error:
        index_wiki(blocker)

    assert "not a directory" in str(error.value)


def test_subdirectories_are_indexed_with_posix_paths(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "nested/deep/page.md", "# 深层页面\n\n内容\n")

    index = index_wiki(root)

    assert [page.path for page in index.pages] == ["nested/deep/page.md"]


def test_extension_parameter(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "page.markdown", "# Other\n\nbody\n")
    write_wiki_page(root, "page.md", "# Default\n\nbody\n")

    index = index_wiki(root, extension=".markdown")

    assert [page.path for page in index.pages] == ["page.markdown"]


def test_bad_front_matter_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "broken.md", '---\nid: "abc"\n# 标题\n')

    index = index_wiki(root)

    assert any("no closing" in warning for warning in index.metadata["warnings"])
    assert index.page("broken.md").title == "标题"


def test_indexing_does_not_modify_the_wiki(tmp_path: Path) -> None:
    wiki = sample_wiki(tmp_path)
    before = {path.name: path.read_bytes() for path in wiki.iterdir()}

    index_wiki(wiki)

    after = {path.name: path.read_bytes() for path in wiki.iterdir()}
    assert before == after


def test_extract_title_prefers_the_first_h1() -> None:
    body = "## 二级\n\n# 一级\n\n正文\n"

    assert extract_title(body, "fallback") == "一级"
    assert extract_title("## 只有二级\n", "fallback") == "只有二级"
    assert extract_title("没有标题\n", "fallback") == "fallback"


def test_display_text_cleans_inline_markup() -> None:
    text = display_text("# 标题\n\n- [解析器](解析器.md) 与 `代码` 与 **粗体**\n")

    assert text == "标题\n\n- 解析器 与 代码 与 粗体\n"
