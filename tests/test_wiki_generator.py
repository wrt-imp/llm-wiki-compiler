"""End to end Wiki Generator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.wiki import (
    GENERATOR_VERSION,
    WikiError,
    WikiGenerator,
    WikiWriteError,
    generate_wiki,
)
from support import concept, document_info, entity, fact, make_kb, relation, src_ref


def sample_kb():
    return make_kb(
        entities=(
            entity(
                "解析器",
                type="system",
                description="把源文件统一成 Document 的组件",
                aliases=("Parser",),
                sources=(src_ref("docA", section_id="docA#1", quote="解析器"),),
            ),
        ),
        concepts=(concept("文档模型", description="结构化表示"),),
        facts=(
            fact(
                "解析器输出文档模型",
                subject="解析器",
                object="文档模型",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器输出文档模型"),),
            ),
        ),
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="produces",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器产出文档模型"),),
            ),
        ),
        documents=(document_info("docA"),),
    )


def test_generates_one_page_per_object_plus_the_index(tmp_path: Path) -> None:
    build = generate_wiki(sample_kb(), tmp_path / "wiki")

    assert [page.path for page in build.pages] == ["解析器.md", "文档模型.md"]
    assert build.written == ["解析器.md", "文档模型.md", "index.md"]
    assert build.counts == {
        "entities": 1,
        "concepts": 1,
        "facts": 1,
        "relations": 1,
        "pages": 2,
        "unattached_facts": 0,
        "unattached_relations": 0,
        "documents": 1,
    }
    assert build.metadata["generator_version"] == GENERATOR_VERSION
    for relative in build.written:
        assert (tmp_path / "wiki" / relative).is_file()


def test_creates_a_missing_output_directory(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"

    build = generate_wiki(sample_kb(), target)

    assert target.is_dir()
    assert (target / "解析器.md").is_file()
    assert build.output_dir == target


def test_chinese_page_names_and_content(tmp_path: Path) -> None:
    generate_wiki(sample_kb(), tmp_path / "wiki")
    text = (tmp_path / "wiki" / "解析器.md").read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert "# 解析器" in text
    assert "把源文件统一成 Document 的组件" in text


def test_empty_knowledge_base_still_writes_an_index(tmp_path: Path) -> None:
    build = generate_wiki(make_kb(), tmp_path / "wiki")

    assert build.pages == []
    assert build.written == ["index.md"]
    assert build.counts["pages"] == 0
    assert any("no entity or concept pages" in warning for warning in build.metadata["warnings"])
    assert (tmp_path / "wiki" / "index.md").is_file()


def test_output_is_byte_for_byte_stable(tmp_path: Path) -> None:
    kb = sample_kb()

    first = generate_wiki(kb, tmp_path / "one")
    second = generate_wiki(kb, tmp_path / "two")

    assert first.written == second.written
    for relative in first.written:
        assert (tmp_path / "one" / relative).read_bytes() == (
            tmp_path / "two" / relative
        ).read_bytes()


def test_regenerating_into_the_same_directory_is_idempotent(tmp_path: Path) -> None:
    generate_wiki(sample_kb(), tmp_path / "wiki")
    before = {path.name: path.read_bytes() for path in (tmp_path / "wiki").iterdir()}

    generate_wiki(sample_kb(), tmp_path / "wiki")
    after = {path.name: path.read_bytes() for path in (tmp_path / "wiki").iterdir()}

    assert before == after


def test_does_not_modify_the_input_knowledge_base(tmp_path: Path) -> None:
    kb = sample_kb()
    before = kb.to_dict()

    generate_wiki(kb, tmp_path / "wiki")

    assert kb.to_dict() == before


def test_rejects_input_that_is_not_a_knowledge_base(tmp_path: Path) -> None:
    with pytest.raises(TypeError) as error:
        generate_wiki({"entities": []}, tmp_path / "wiki")  # type: ignore[arg-type]

    assert "KnowledgeBase" in str(error.value)
    assert not (tmp_path / "wiki").exists()


def test_write_errors_name_the_path(tmp_path: Path) -> None:
    blocker = tmp_path / "wiki"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(WikiWriteError) as error:
        generate_wiki(sample_kb(), blocker)

    assert str(blocker) in str(error.value)
    assert isinstance(error.value, WikiError)


def test_overwrite_false_refuses_to_replace_pages(tmp_path: Path) -> None:
    generate_wiki(sample_kb(), tmp_path / "wiki")

    with pytest.raises(WikiWriteError) as error:
        WikiGenerator(tmp_path / "wiki", overwrite=False).generate(sample_kb())

    assert "overwrite is disabled" in str(error.value)


def test_index_can_be_disabled(tmp_path: Path) -> None:
    kb = sample_kb()
    kb.facts[0].subject = "不存在的对象"
    kb.facts[0].object = "也不存在"

    build = generate_wiki(kb, tmp_path / "wiki", include_index=False)

    assert "index.md" not in build.written
    assert not (tmp_path / "wiki" / "index.md").exists()
    assert any("index page is disabled" in warning for warning in build.metadata["warnings"])


def test_no_links_in_the_generated_files(tmp_path: Path) -> None:
    build = generate_wiki(sample_kb(), tmp_path / "wiki")

    for relative in build.written:
        text = (tmp_path / "wiki" / relative).read_text(encoding="utf-8")
        assert "[[" not in text
        assert "]](" not in text
        assert "](" not in text


def test_generator_keeps_page_metadata_for_the_link_resolver(tmp_path: Path) -> None:
    build = generate_wiki(sample_kb(), tmp_path / "wiki")
    page = build.pages[0]

    assert page.kind == "entity"
    assert page.object_id
    assert page.title == "解析器"
    assert page.aliases == ("Parser",)
