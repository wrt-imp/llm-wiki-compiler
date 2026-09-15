"""Source presentation tests: nothing may be lost, everything traceable."""

from __future__ import annotations

import re

from compiler.wiki import (
    MAX_QUOTE_CHARS,
    assign_page_paths,
    build_plan,
    ordered_sources,
    render_index,
    render_page,
    source_line,
)
from support import concept, document_info, entity, fact, make_kb, relation, src_ref


def all_source_keys(items) -> set:
    keys = set()
    for collection in (items.entities, items.concepts, items.facts, items.relations):
        for item in collection:
            for ref in item.sources:
                keys.add((ref.document_id, ref.section_id, ref.page_number, ref.quote))
    return keys


def rendered_texts(kb) -> dict:
    plan = build_plan(kb)
    pages = assign_page_paths([page_plan.target for page_plan in plan.pages])
    texts = {
        page.path: render_page(page, page_plan)
        for page, page_plan in zip(pages, plan.pages)
    }
    texts["index.md"] = render_index(plan, pages)
    return texts


def sample_kb():
    return make_kb(
        entities=(
            entity(
                "解析器",
                description="组件",
                aliases=("Parser",),
                sources=(src_ref("docA", section_id="docA#1", page_number=3, quote="解析器的说明"),),
            ),
        ),
        concepts=(
            concept("文档模型", sources=(src_ref("docA", section_id="docA#2", quote="文档模型"),)),
        ),
        facts=(
            fact(
                "解析器输出文档模型",
                subject="解析器",
                object="文档模型",
                sources=(
                    src_ref("docA", section_id="docA#1", page_number=3, quote="解析器输出文档模型"),
                    src_ref("docB", section_id="docB#5", quote="Parser produces the document model"),
                ),
            ),
        ),
        documents=(document_info("docA"), document_info("docB")),
    )


def test_source_line_shows_document_section_page_and_quote() -> None:
    line = source_line(
        1, src_ref("docA", section_id="docA#1", page_number=3, quote="引用文本")
    )

    assert line == '1. **docA** · section `docA#1` · page 3 — “引用文本”'


def test_source_line_without_section_or_page() -> None:
    assert source_line(2, src_ref("docB", quote="只有文档")) == '2. **docB** — “只有文档”'


def test_long_quotes_are_truncated() -> None:
    line = source_line(1, src_ref("docA", quote="字" * (MAX_QUOTE_CHARS + 50)))

    assert line.endswith("…”")
    assert len(line) < MAX_QUOTE_CHARS + 50


def test_sources_are_ordered_and_deduplicated() -> None:
    first = src_ref("docB", section_id="docB#1", quote="b")
    second = src_ref("docA", section_id="docA#1", quote="a")
    duplicate = src_ref("docB", section_id="docB#1", quote="b")

    ordered = ordered_sources([[first, second], [duplicate]])

    assert [(source.document_id, source.quote) for source in ordered] == [
        ("docA", "a"),
        ("docB", "b"),
    ]


def test_source_numbering_does_not_depend_on_input_order() -> None:
    forward = sample_kb()
    backward = sample_kb()
    backward.entities[0].sources.reverse()
    backward.facts[0].sources.reverse()

    assert rendered_texts(forward)["解析器.md"] == rendered_texts(backward)["解析器.md"]


def test_page_sources_include_the_evidence_of_its_facts() -> None:
    page = rendered_texts(sample_kb())["解析器.md"]
    sources_section = page.split("## Sources")[1]

    # own source (docA#1) plus the fact evidence from docA#1 and docB#5
    assert "section `docA#1`" in sources_section
    assert "section `docB#5`" in sources_section
    assert "解析器的说明" in sources_section
    assert "Parser produces the document model" in sources_section


def test_fact_markers_match_the_numbered_sources() -> None:
    page = rendered_texts(sample_kb())["解析器.md"]
    fact_line = [
        line
        for line in page.splitlines()
        if line.startswith("- 解析器输出文档模型")
    ][0]
    sources_section = page.split("## Sources")[1]

    markers = re.findall(r"\[(\d+)\]", fact_line)
    assert len(markers) == 2
    assert markers == sorted(set(markers), key=int)
    for number in markers:
        assert re.search(rf"^{number}\. ", sources_section, re.M)


def test_every_knowledge_base_source_reaches_the_wiki() -> None:
    kb = sample_kb()
    kb.relations.append(
        relation(
            "不存在的对象",
            "也不存在",
            type="related to",
            sources=[src_ref("docZ", section_id="docZ#7", quote="孤立的关系")],
        )
    )
    texts = rendered_texts(kb)
    combined = "\n".join(texts.values())

    for document_id, section_id, page_number, quote in all_source_keys(kb):
        assert document_id in combined
        assert quote in combined
        if section_id:
            assert section_id in combined
