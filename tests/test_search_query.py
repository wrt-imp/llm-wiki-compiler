"""Query tests: matching, ranking, stability."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.linker import resolve_wiki
from compiler.search import (
    SCORE_ALIAS_EXACT,
    SCORE_ALIAS_CONTAINS,
    SCORE_BODY_CONTAINS,
    SCORE_TITLE_EXACT,
    index_wiki,
    search,
    search_wiki,
)
from support import build_sample_wiki, write_wiki_page


def sample_index(tmp_path: Path):
    build = build_sample_wiki(tmp_path)
    resolve_wiki(build)
    return index_wiki(tmp_path / "wiki")


def paths(results) -> list:
    return [result.path for result in results]


def test_title_search_ranks_first(tmp_path: Path) -> None:
    results = search(sample_index(tmp_path), "解析器")

    assert results[0].path == "解析器.md"
    assert results[0].title == "解析器"
    assert results[0].score == SCORE_TITLE_EXACT
    assert results[0].matched_in == ("title",)
    assert results[0].kind == "entity"
    assert results[0].object_id == "a7755ec09b9f5bed"


def test_body_matches_come_after_title_matches(tmp_path: Path) -> None:
    results = search(sample_index(tmp_path), "解析器")

    assert paths(results) == [
        "解析器.md",
        "index.md",
        "文档模型.md",
        "知识图谱编译器.md",
    ]
    assert results[1].score == SCORE_BODY_CONTAINS
    assert results[1].matched_in == ("body",)


def test_alias_search(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    by_alias = search(index, "Parser")

    assert paths(by_alias) == ["解析器.md"]
    assert by_alias[0].score == SCORE_ALIAS_EXACT
    assert by_alias[0].matched_in == ("alias",)
    assert paths(search(index, "Document Model")) == ["文档模型.md"]
    assert search(index, "Document Model")[0].score == SCORE_ALIAS_EXACT


def test_partial_alias_words_get_a_lower_score(tmp_path: Path) -> None:
    results = search(sample_index(tmp_path), "Document")

    assert results[0].path == "文档模型.md"
    assert results[0].score == SCORE_ALIAS_CONTAINS
    assert results[0].matched_in == ("alias",)


def test_body_search_only(tmp_path: Path) -> None:
    results = search(sample_index(tmp_path), "统一成")

    assert paths(results) == ["解析器.md"]
    assert results[0].score == SCORE_BODY_CONTAINS
    assert "统一成" in results[0].snippet


def test_chinese_keywords(tmp_path: Path) -> None:
    results = search(sample_index(tmp_path), "知识图谱编译器")

    assert results[0].path == "知识图谱编译器.md"
    assert results[0].score == SCORE_TITLE_EXACT
    assert "知识图谱编译器" in results[0].snippet


def test_search_is_case_insensitive(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    lower = search(index, "parser")
    upper = search(index, "PARSER")
    mixed = search(index, "Parser")

    assert lower == upper == mixed


def test_multiple_keywords_are_required(tmp_path: Path) -> None:
    results = search(sample_index(tmp_path), "解析器 文档模型")

    assert paths(results) == ["文档模型.md", "解析器.md", "index.md"]
    assert [result.score for result in results] == [101, 101, 2]
    assert "知识图谱编译器.md" not in paths(results)


def test_missing_keyword_excludes_the_page(tmp_path: Path) -> None:
    assert search(sample_index(tmp_path), "解析器 不存在的词") == []


def test_no_results(tmp_path: Path) -> None:
    assert search(sample_index(tmp_path), "存在主义") == []


def test_scores_tie_break_on_path(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    results = search(index, "解析器")
    body_matches = [result for result in results if result.score == SCORE_BODY_CONTAINS]

    assert [result.path for result in body_matches] == sorted(
        result.path for result in body_matches
    )


def test_repeated_queries_return_identical_results(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    assert search(index, "解析器") == search(index, "解析器")
    assert [result.snippet for result in search(index, "解析器")] == [
        result.snippet for result in search(index, "解析器")
    ]


def test_limit_caps_the_results(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    assert len(search(index, "解析器", limit=2)) == 2
    assert search(index, "解析器", limit=0) == []


def test_special_characters_are_matched_literally(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    assert paths(search(index, "文档模型"))[0] == "文档模型.md"
    assert search(index, "文档*模型") == []
    assert search(index, "[[解析器]]") == []
    assert search(index, "解析器)") == []
    assert search(index, "%%%") == []


def test_empty_query_is_rejected(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    with pytest.raises(ValueError):
        search(index, "")
    with pytest.raises(ValueError):
        search(index, "   ")


def test_empty_wiki_returns_no_results(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    root.mkdir()
    index = index_wiki(root)

    assert index.pages == []
    assert search(index, "解析器") == []


def test_front_matter_is_never_matched(tmp_path: Path) -> None:
    index = sample_index(tmp_path)

    assert search(index, "a7755ec09b9f5bed") == []
    assert search(index, "kind") == []


def test_search_does_not_modify_the_wiki(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)
    resolve_wiki(build)
    wiki = tmp_path / "wiki"
    before = {path.name: path.read_bytes() for path in wiki.iterdir()}

    search(index_wiki(wiki), "解析器")

    after = {path.name: path.read_bytes() for path in wiki.iterdir()}
    assert before == after


def test_search_wiki_convenience(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)
    resolve_wiki(build)

    direct = search_wiki(tmp_path / "wiki", "Parser")

    assert paths(direct) == ["解析器.md"]
    assert direct[0].kind == "entity"


def test_search_of_a_hand_written_page(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    write_wiki_page(root, "note.md", "# 随笔\n\n记录一些关于解析器的想法\n")

    results = search(index_wiki(root), "解析器")

    assert paths(results) == ["note.md"]
    assert results[0].kind == "page"
