"""Markdown rendering tests for pages and the index."""

from __future__ import annotations

import re
from typing import Any, Dict, List

import pytest

from compiler.knowledge import KnowledgeBase
from compiler.wiki import (
    PageTarget,
    WikiPage,
    assign_page_paths,
    build_plan,
    render_index,
    render_page,
)
from support import (
    concept,
    document_info,
    entity,
    fact,
    make_kb,
    relation,
    src_ref,
)


def sample_kb() -> KnowledgeBase:
    return make_kb(
        entities=(
            entity(
                "解析器",
                type="system",
                description="把源文件统一成 Document 的组件",
                aliases=("Parser",),
                sources=(src_ref("docA", section_id="docA#1", quote="解析器把 PDF 统一成 Document"),),
            ),
            entity(
                "知识图谱编译器",
                type="system",
                description="把文档编译成知识 wiki 的系统",
                sources=(src_ref("docB", section_id="docB#2", quote="知识图谱编译器"),),
            ),
        ),
        concepts=(
            concept(
                "文档模型",
                description="解析结果的结构化表示",
                sources=(src_ref("docA", section_id="docA#1", quote="文档模型"),),
            ),
        ),
        facts=(
            fact(
                "解析器把 PDF、Markdown、TXT 统一成 Document",
                subject="解析器",
                predicate="输出",
                object="Document",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器把 PDF、Markdown、TXT 统一成 Document"),),
            ),
            fact(
                "没有归属的事实",
                subject="不存在的对象",
                object="也不存在",
                sources=(src_ref("docC", section_id="docC#9", quote="没有归属的事实"),),
            ),
        ),
        relations=(
            relation(
                "知识图谱编译器",
                "解析器",
                type="uses",
                description="调用解析器",
                sources=(src_ref("docB", section_id="docB#2", quote="调用解析器"),),
            ),
            relation(
                "解析器",
                "文档模型",
                type="produces",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器产出文档模型"),),
            ),
        ),
        documents=(document_info("docA"), document_info("docB")),
    )


def rendered_pages(kb: KnowledgeBase, **kwargs: Any) -> Dict[str, str]:
    plan = build_plan(kb)
    pages = assign_page_paths(
        [page_plan.target for page_plan in plan.pages],
        reserved={"index"},
    )
    return {
        page.path: render_page(page, page_plan, **kwargs)
        for page, page_plan in zip(pages, plan.pages)
    }


def test_entity_page_has_title_description_and_front_matter() -> None:
    pages = rendered_pages(sample_kb())
    page = pages["解析器.md"]

    assert page.startswith("---\n")
    assert "# 解析器\n" in page
    assert "## Description\n\n把源文件统一成 Document 的组件" in page
    assert 'kind: "entity"' in page
    assert 'type: "system"' in page
    assert 'aliases:\n  - "Parser"' in page
    assert 'page: "解析器.md"' in page


def test_concept_page_has_no_type() -> None:
    pages = rendered_pages(sample_kb())
    page = pages["文档模型.md"]

    assert "# 文档模型" in page
    assert 'kind: "concept"' in page
    assert "type:" not in page


def test_front_matter_can_be_disabled() -> None:
    pages = rendered_pages(sample_kb(), front_matter=False)

    assert all(not page.startswith("---") for page in pages.values())
    assert pages["解析器.md"].startswith("# 解析器\n")


def test_front_matter_is_valid_yaml() -> None:
    yaml = pytest.importorskip("yaml")
    pages = rendered_pages(sample_kb())
    block = pages["解析器.md"].split("---\n")[1]

    data = yaml.safe_load(block)

    assert data["id"]
    assert data["kind"] == "entity"
    assert data["type"] == "system"
    assert data["aliases"] == ["Parser"]
    assert data["page"] == "解析器.md"


def test_fact_is_attached_to_every_matching_page() -> None:
    kb = sample_kb()
    kb.facts.append(
        fact("解析器输出文档模型", subject="解析器", object="文档模型")
    )

    pages = rendered_pages(kb)

    assert "解析器输出文档模型" in pages["解析器.md"]
    assert "解析器输出文档模型" in pages["文档模型.md"]
    # the other fact mentions "Document", which is not a page
    assert "解析器把 PDF、Markdown、TXT 统一成 Document" not in pages["文档模型.md"]
    assert "## Facts" not in pages["知识图谱编译器.md"]


def test_fact_without_a_page_is_unattached() -> None:
    plan = build_plan(sample_kb())

    assert [item.statement for item in plan.unattached_facts] == ["没有归属的事实"]


def test_unattached_items_end_up_in_the_index() -> None:
    kb = sample_kb()
    plan = build_plan(kb)
    pages = assign_page_paths([page_plan.target for page_plan in plan.pages])

    index = render_index(plan, pages)

    assert "## Unattached Facts" in index
    assert "没有归属的事实" in index
    assert "## Unattached Relations" in index
    assert "- (none)" in index


def test_relation_direction_is_visible_on_both_pages() -> None:
    pages = rendered_pages(sample_kb())

    # source side: plain triple; target side: the same triple marked as incoming
    assert "知识图谱编译器 —uses→ 解析器" in pages["知识图谱编译器.md"]
    assert "← 知识图谱编译器 —uses→ 解析器" in pages["解析器.md"]
    assert "解析器 —produces→ 文档模型" in pages["解析器.md"]
    assert "← 解析器 —produces→ 文档模型" in pages["文档模型.md"]


def test_self_relation_is_rendered_once() -> None:
    kb = make_kb(
        entities=(entity("解析器", aliases=("Parser",)),),
        relations=(relation("解析器", "解析器", type="depends on"),),
    )
    pages = rendered_pages(kb)
    body = pages["解析器.md"]

    assert body.count("解析器 —depends on→ 解析器") == 1


def test_empty_sections_are_omitted() -> None:
    kb = make_kb(entities=(entity("孤立的实体"),))
    page = rendered_pages(kb)["孤立的实体.md"]

    assert "## Facts" not in page
    assert "## Relations" not in page
    assert "## Sources" not in page
    assert "## Description" not in page


def test_pages_are_sorted_entities_first_then_concepts() -> None:
    plan = build_plan(sample_kb())

    assert [page_plan.target.kind for page_plan in plan.pages] == [
        "entity",
        "entity",
        "concept",
    ]
    assert [page_plan.target.title for page_plan in plan.pages][0] == "知识图谱编译器"


def test_index_lists_documents_and_pages() -> None:
    kb = sample_kb()
    plan = build_plan(kb)
    pages = assign_page_paths([page_plan.target for page_plan in plan.pages])

    index = render_index(plan, pages)

    assert "# Knowledge Wiki" in index
    assert "2 document(s)" in index
    assert "2 entity page(s)" in index
    assert "- `docA` — title of docA (docA.md)" in index
    assert "- 解析器 → 解析器.md" in index
    assert "- 文档模型 → 文档模型.md" in index


def test_no_links_are_generated() -> None:
    kb = sample_kb()
    plan = build_plan(kb)
    pages = assign_page_paths([page_plan.target for page_plan in plan.pages])
    texts: List[str] = [
        render_page(page, page_plan)
        for page, page_plan in zip(pages, plan.pages)
    ]
    texts.append(render_index(plan, pages))

    for text in texts:
        assert "[[" not in text
        assert "]]" not in text
        assert "](" not in text
        assert "http://" not in text and "https://" not in text


def test_source_markers_point_at_the_source_list() -> None:
    page = rendered_pages(sample_kb())["解析器.md"]
    sources_section = page.split("## Sources")[1]

    assert " [1]" in page
    assert re.search(r"^1\. \*\*docA\*\*", sources_section, re.M)
    assert re.search(r"^\d+\. \*\*docB\*\*", sources_section, re.M)


def test_render_page_accepts_a_handmade_page() -> None:
    kb = make_kb(entities=(entity("解析器", description="d"),))
    plan = build_plan(kb)
    page = WikiPage(
        path="解析器.md",
        kind="entity",
        object_id=plan.pages[0].target.object_id,
        title="解析器",
    )

    text = render_page(page, plan.pages[0], front_matter=False)

    assert text.startswith("# 解析器\n")


def test_page_plan_keeps_the_target_and_its_relations() -> None:
    plan = build_plan(sample_kb())
    parser_page = [
        page_plan for page_plan in plan.pages if page_plan.target.title == "解析器"
    ][0]

    assert isinstance(parser_page.target, PageTarget)
    assert parser_page.target.kind == "entity"
    assert parser_page.target.aliases == ("Parser",)
    assert [
        (slot.relation.type, slot.direction) for slot in parser_page.relations
    ] == [("uses", "in"), ("produces", "out")]
