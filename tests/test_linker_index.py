"""Link index tests: names, aliases, ambiguity."""

from __future__ import annotations

from pathlib import Path

from compiler.knowledge import KnowledgeBase
from compiler.linker import build_link_index
from support import build_sample_wiki, concept, entity, make_kb, src_ref


def test_index_maps_titles_and_aliases(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)

    index = build_link_index(build)

    assert index.lookup("解析器").path == "解析器.md"
    assert index.lookup("Parser").path == "解析器.md"
    assert index.lookup("文档模型").path == "文档模型.md"
    assert index.lookup("Document Model").path == "文档模型.md"


def test_index_is_case_and_space_insensitive(tmp_path: Path) -> None:
    index = build_link_index(build_sample_wiki(tmp_path))

    assert index.lookup("parser").path == "解析器.md"
    assert index.lookup("  PARSER  ").path == "解析器.md"
    assert index.lookup("document   model").path == "文档模型.md"


def test_unknown_names_are_not_indexed(tmp_path: Path) -> None:
    index = build_link_index(build_sample_wiki(tmp_path))

    assert index.lookup("不存在的对象") is None
    assert index.is_ambiguous("不存在的对象") is False


def test_keys_are_sorted_longest_first(tmp_path: Path) -> None:
    index = build_link_index(build_sample_wiki(tmp_path))

    lengths = [len(key) for key in index.keys]

    assert lengths == sorted(lengths, reverse=True)


def test_paths_lists_every_page(tmp_path: Path) -> None:
    index = build_link_index(build_sample_wiki(tmp_path))

    assert sorted(index.paths) == ["文档模型.md", "知识图谱编译器.md", "解析器.md"]


def test_same_title_entity_and_concept_is_ambiguous(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(entity("Python", type="system", description="一种编程语言"),),
        concepts=(concept("python", description="编程语言这个概念"),),
    )
    build = build_sample_wiki(tmp_path, kb)

    index = build_link_index(build)

    assert index.lookup("Python") is None
    assert index.is_ambiguous("PYTHON") is True
    assert sorted(page.path for page in index.candidates("python")) == [
        "Python-entity.md",
        "python-concept.md",
    ]
    assert "python" in index.ambiguous_keys


def test_index_of_an_empty_wiki(tmp_path: Path) -> None:
    index = build_link_index(build_sample_wiki(tmp_path, KnowledgeBase()))

    assert index.keys == []
    assert index.paths == []


def test_index_keeps_alias_of_a_collision_renamed_page(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("解析器", aliases=("Parser",), sources=(src_ref("docA"),)),
        ),
    )

    index = build_link_index(build_sample_wiki(tmp_path, kb))

    assert index.lookup("Parser").path.endswith(".md")
    assert index.lookup("Parser").title == "解析器"
