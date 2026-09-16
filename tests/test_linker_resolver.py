"""End to end Link Resolution tests on generated wiki pages."""

from __future__ import annotations

import posixpath
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from compiler.knowledge import KnowledgeBase
from compiler.linker import (
    LinkWriteError,
    build_link_index,
    find_link_targets,
    link_text,
    resolve_wiki,
)
from compiler.wiki import WikiBuild
from support import (
    build_sample_wiki,
    concept,
    document_info,
    entity,
    fact,
    make_kb,
    src_ref,
    wiki_kb,
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolve(
    tmp_path: Path, kb: Optional[KnowledgeBase] = None, **options
) -> Tuple[WikiBuild, object, Path]:
    build = build_sample_wiki(tmp_path, kb)
    result = resolve_wiki(build, **options)
    return build, result, tmp_path / "wiki"


def front_matter(text: str) -> str:
    parts = text.split("---")
    return parts[1] if text.startswith("---") and len(parts) > 1 else ""


# ----------------------------------------------------------------------
# 1 - 4: titles, aliases, Chinese, mutual links
# ----------------------------------------------------------------------
def test_title_becomes_a_link(tmp_path: Path) -> None:
    _, result, wiki = resolve(tmp_path)

    text = read(wiki / "知识图谱编译器.md")

    assert "[解析器](解析器.md)" in text
    assert result.links > 0


def test_chinese_titles_and_targets_are_kept_readable(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path)

    text = read(wiki / "解析器.md")

    assert "[文档模型](文档模型.md)" in text
    assert "%E8%A7%A3" not in text


def test_alias_becomes_a_link(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("解析器", aliases=("Parser",), description="组件"),
            entity("知识图谱编译器", description="Parser 是解析组件"),
        ),
    )

    _, _, wiki = resolve(tmp_path, kb)

    # the alias is on another page: on the entity's own page it would be a self
    # reference (and self references are not linked by default)
    assert "[Parser](解析器.md)" in read(wiki / "知识图谱编译器.md")


def test_alias_in_lower_case_still_matches(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("解析器", aliases=("Parser",)),
            entity("知识图谱编译器", description="parser converts sources"),
        ),
    )

    _, _, wiki = resolve(tmp_path, kb)

    assert "[parser](解析器.md)" in read(wiki / "知识图谱编译器.md")


def test_pages_link_to_each_other(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path)

    assert "[文档模型](文档模型.md)" in read(wiki / "解析器.md")
    assert "[解析器](解析器.md)" in read(wiki / "文档模型.md")


# ----------------------------------------------------------------------
# 5 - 8: missing targets, self references, repeats, boundaries
# ----------------------------------------------------------------------
def test_unknown_names_stay_plain_text(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(entity("解析器", description="提到了不存在的对象"),),
    )

    _, result, wiki = resolve(tmp_path, kb)
    text = read(wiki / "解析器.md")

    assert "不存在的对象" in text
    assert "[不存在的对象]" not in text
    assert result.counts["dead_links"] == 0


def test_self_references_are_not_linked(tmp_path: Path) -> None:
    _, result, wiki = resolve(tmp_path)
    text = read(wiki / "解析器.md")

    # the relation renders as "解析器 —produces→ 文档模型"
    assert "- 解析器 —produces→ [文档模型](文档模型.md)" in text
    assert result.counts["skipped_self"] > 0


def test_self_references_can_be_linked_on_request(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path, allow_self_links=True)
    text = read(wiki / "解析器.md")

    assert "[解析器](解析器.md) —produces→" in text


def test_repeated_mentions_are_all_linked(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("解析器", description="文档模型 文档模型 文档模型"),
            entity("文档模型", description="概念"),
        ),
    )

    _, result, wiki = resolve(tmp_path, kb)
    text = read(wiki / "解析器.md")

    assert text.count("[文档模型](文档模型.md)") == 3
    assert result.links >= 3


def test_ascii_names_respect_word_boundaries(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("Parser", description="Document Model and Documenter"),
            entity("Document", description="A document page"),
        ),
    )

    _, _, wiki = resolve(tmp_path, kb)
    text = read(wiki / "Parser.md")

    # "Documenter" must not be turned into "[Document]er"
    assert "[Document]er" not in text
    assert "[Document](Document.md)" in text


def test_chinese_names_match_inside_prose(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("解析器", description="组件"),
            entity("知识图谱编译器", description="使用解析器把文档编译成 wiki"),
        ),
    )

    _, _, wiki = resolve(tmp_path, kb)
    text = read(wiki / "知识图谱编译器.md")

    assert "[解析器](解析器.md)把文档编译成 wiki" in text


def test_longest_known_name_wins(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("解析器", description="短名"),
            entity("解析器阶段", description="长名"),
            entity("知识图谱编译器", description="包含解析器阶段这个词"),
        ),
    )

    _, _, wiki = resolve(tmp_path, kb)
    text = read(wiki / "知识图谱编译器.md")

    assert "[解析器阶段](解析器阶段.md)" in text
    assert "[解析器](解析器.md)阶段" not in text


# ----------------------------------------------------------------------
# 9 - 11: code, inline code, existing links
# ----------------------------------------------------------------------
def test_fenced_code_blocks_are_not_linked(tmp_path: Path) -> None:
    build, _, wiki = resolve(tmp_path)
    page = wiki / "解析器.md"
    page.write_text(
        read(page) + "\n```python\n解析器 = 'not a link'\n```\n",
        encoding="utf-8",
        newline="\n",
    )

    resolve_wiki(build)
    text = read(page)

    assert "解析器 = 'not a link'" in text
    assert "[解析器] = 'not a link'" not in text


def test_inline_code_is_not_linked(tmp_path: Path) -> None:
    kb = make_kb(entities=(entity("解析器", description="组件"), entity("文档模型")))
    index = build_link_index(_memory_build(kb))

    linked = link_text("`文档模型` 与 文档模型", index, from_path="解析器.md")

    assert linked.text == "`文档模型` 与 [文档模型](文档模型.md)"
    assert linked.links == 1


def test_existing_links_are_not_linked_again(tmp_path: Path) -> None:
    build, _, wiki = resolve(tmp_path)
    page = wiki / "解析器.md"
    page.write_text(
        "[文档模型](文档模型.md) 与 [[文档模型]]\n",
        encoding="utf-8",
        newline="\n",
    )

    resolve_wiki(build)
    text = read(page)

    assert text == "[文档模型](文档模型.md) 与 [[文档模型]]\n"


def test_resolving_twice_is_idempotent(tmp_path: Path) -> None:
    build, first, wiki = resolve(tmp_path)
    before = {path.name: path.read_bytes() for path in wiki.iterdir()}

    second = resolve_wiki(build)
    after = {path.name: path.read_bytes() for path in wiki.iterdir()}

    assert before == after
    assert second.counts["links"] == 0
    assert first.links > 0


# ----------------------------------------------------------------------
# 12 - 14: paths, special file names, ambiguity
# ----------------------------------------------------------------------
def test_links_never_contain_backslashes(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path)

    for path in wiki.iterdir():
        assert "\\" not in read(path)


def test_special_file_names_are_encoded_and_resolve(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(
            entity("my page", description="a page with a space"),
            entity("a[b]c", description="a page with brackets"),
        ),
        facts=(fact("my page uses a[b]c", subject="my page", object="a[b]c"),),
    )

    _, _, wiki = resolve(tmp_path, kb)

    assert "[my page](my%20page.md)" in read(wiki / "a[b]c.md")
    assert "[a\\[b\\]c](a%5Bb%5Dc.md)" in read(wiki / "my page.md")
    assert (wiki / "a[b]c.md").is_file()
    assert (wiki / "my page.md").is_file()


def test_same_title_entity_and_concept_is_not_linked(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(entity("Python", description="Python 是一种编程语言"),),
        concepts=(concept("python", description="Python 也可以指这个概念"),),
    )

    _, result, wiki = resolve(tmp_path, kb)

    assert "[Python]" not in read(wiki / "Python-entity.md")
    assert "python" in result.metadata["ambiguous_names"]
    assert result.counts["skipped_ambiguous"] > 0


def test_ambiguous_names_can_prefer_the_entity(tmp_path: Path) -> None:
    kb = make_kb(
        entities=(entity("Python", description="Python 是一种编程语言"),),
        concepts=(concept("python", description="Python 也可以指这个概念"),),
    )

    _, _, wiki = resolve(tmp_path, kb, on_ambiguous="prefer_entity")

    assert "[Python](Python-entity.md)" in read(wiki / "python-concept.md")


def test_invalid_options_are_rejected(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)

    with pytest.raises(ValueError):
        resolve_wiki(build, style="html")
    with pytest.raises(ValueError):
        resolve_wiki(build, on_ambiguous="whatever")


# ----------------------------------------------------------------------
# 15 - 17: input safety, stability, no dead links
# ----------------------------------------------------------------------
def test_knowledge_base_is_not_modified(tmp_path: Path) -> None:
    kb = wiki_kb()
    before = kb.to_dict()

    build = build_sample_wiki(tmp_path, kb)
    resolve_wiki(build)

    assert kb.to_dict() == before


def test_output_is_stable_across_runs(tmp_path: Path) -> None:
    first_build = build_sample_wiki(tmp_path / "one", wiki_kb())
    resolve_wiki(first_build)
    second_build = build_sample_wiki(tmp_path / "two", wiki_kb())
    resolve_wiki(second_build)

    one = tmp_path / "one" / "wiki"
    two = tmp_path / "two" / "wiki"
    assert sorted(path.name for path in one.iterdir()) == sorted(
        path.name for path in two.iterdir()
    )
    for path in one.iterdir():
        assert path.read_bytes() == (two / path.name).read_bytes()


def test_output_does_not_depend_on_page_order(tmp_path: Path) -> None:
    kb = wiki_kb()
    reversed_kb = make_kb(
        entities=tuple(reversed(kb.entities)),
        concepts=tuple(kb.concepts),
        facts=tuple(kb.facts),
        relations=tuple(kb.relations),
        documents=tuple(kb.documents),
    )

    first = build_sample_wiki(tmp_path / "one", kb)
    resolve_wiki(first)
    second = build_sample_wiki(tmp_path / "two", reversed_kb)
    resolve_wiki(second)

    assert read(tmp_path / "one" / "wiki" / "解析器.md") == read(
        tmp_path / "two" / "wiki" / "解析器.md"
    )


def test_no_dead_links_are_produced(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path)

    checked = 0
    for path in wiki.iterdir():
        for target in find_link_targets(read(path)):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), (path.name, target)
            checked += 1
    assert checked > 0


def test_front_matter_is_untouched(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)
    page = tmp_path / "wiki" / "解析器.md"
    before = front_matter(read(page))

    resolve_wiki(build)

    assert front_matter(read(page)) == before
    assert 'page: "解析器.md"' in read(page)


def test_sources_section_is_left_alone(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path)
    sources = read(wiki / "解析器.md").split("## Sources")[1]

    assert "“解析器输出文档模型”" in sources
    assert "[文档模型]" not in sources


def test_sources_can_be_linked_on_request(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path, link_sources=True)
    sources = read(wiki / "解析器.md").split("## Sources")[1]

    assert "[文档模型](文档模型.md)" in sources


def test_index_page_names_are_linked_but_file_names_are_not(tmp_path: Path) -> None:
    _, _, wiki = resolve(tmp_path)
    index = read(wiki / "index.md")

    assert "[解析器](解析器.md) → 解析器.md" in index
    assert "[解析器](解析器.md).md" not in index


def test_result_reports_the_run(tmp_path: Path) -> None:
    _, result, _ = resolve(tmp_path)

    assert result.counts["files"] == 4
    assert result.counts["pages"] == 3
    assert result.counts["links"] > 0
    assert result.counts["dead_links"] == 0
    assert result.metadata["style"] == "markdown"
    assert result.metadata["index_size"] > 0
    assert sorted(result.files) == sorted(
        ["解析器.md", "文档模型.md", "知识图谱编译器.md", "index.md"]
    )


def test_separate_output_keeps_the_original_wiki(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)
    original = read(tmp_path / "wiki" / "解析器.md")

    result = resolve_wiki(build, in_place=False, output_dir=tmp_path / "linked")

    assert read(tmp_path / "wiki" / "解析器.md") == original
    assert "[文档模型](文档模型.md)" in read(tmp_path / "linked" / "解析器.md")
    assert result.output_dir == tmp_path / "linked"


def test_write_errors_name_the_path(tmp_path: Path) -> None:
    build = build_sample_wiki(tmp_path)
    blocker = tmp_path / "linked"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(LinkWriteError) as error:
        resolve_wiki(build, in_place=False, output_dir=blocker)

    assert str(blocker) in str(error.value)


# ----------------------------------------------------------------------
# helpers for tests that need a hand written page
# ----------------------------------------------------------------------
def _build(tmp_path: Path) -> WikiBuild:
    return build_sample_wiki(tmp_path)


def _memory_build(kb: KnowledgeBase) -> WikiBuild:
    from compiler.wiki import WikiBuild, WikiPage

    return WikiBuild(
        output_dir=Path("."),
        pages=[
            WikiPage(
                path=f"{item.name}.md",
                kind=kind,
                object_id=item.id,
                title=item.name,
                aliases=tuple(item.aliases),
            )
            for kind, collection in (("entity", kb.entities), ("concept", kb.concepts))
            for item in collection
        ],
    )
