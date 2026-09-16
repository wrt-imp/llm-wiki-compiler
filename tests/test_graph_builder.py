"""KnowledgeBase -> Graph conversion tests."""

from __future__ import annotations

import json

import pytest

from compiler.graph import (
    KIND_CONCEPT,
    KIND_ENTITY,
    build_graph,
)
from compiler.knowledge import KnowledgeBase, make_knowledge_id
from support import concept, document_info, entity, fact, make_kb, relation, src_ref


def sample_kb() -> KnowledgeBase:
    parser = entity(
        "解析器",
        type="system",
        description="组件",
        aliases=("Parser",),
        sources=(src_ref("docA", quote="解析器"),),
    )
    model = concept(
        "文档模型",
        description="结构",
        aliases=("Document Model",),
        sources=(src_ref("docA", quote="文档模型"),),
    )
    return make_kb(
        entities=(parser,),
        concepts=(model,),
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="produces",
                description="产出",
                sources=(src_ref("docA", quote="解析器产出文档模型"),),
            ),
        ),
        facts=(
            fact(
                "解析器输出文档模型",
                subject="解析器",
                predicate="输出",
                object="文档模型",
                sources=(src_ref("docB", quote="解析器输出文档模型"),),
            ),
        ),
        documents=(document_info("docA"), document_info("docB")),
    )


def test_entity_and_concept_become_nodes() -> None:
    graph = build_graph(sample_kb())

    entity_node = graph.get_node(make_knowledge_id("entity", "解析器"))
    concept_node = graph.get_node(make_knowledge_id("concept", "文档模型"))

    assert entity_node.kind == KIND_ENTITY
    assert entity_node.title == "解析器"
    assert entity_node.aliases == ("Parser",)
    assert entity_node.metadata["type"] == "system"
    assert entity_node.metadata["sources"][0].document_id == "docA"
    assert concept_node.kind == KIND_CONCEPT
    assert "type" not in concept_node.metadata


def test_relation_becomes_an_edge_with_names() -> None:
    graph = build_graph(sample_kb())
    edges = [edge for edge in graph.get_edges() if edge.kind == "relation"]

    assert len(edges) == 1
    edge = edges[0]
    assert edge.source == "解析器"
    assert edge.target == "文档模型"
    assert edge.type == "produces"
    assert edge.metadata["source_id"] == make_knowledge_id("entity", "解析器")
    assert edge.metadata["target_id"] == make_knowledge_id("concept", "文档模型")
    assert edge.metadata["description"] == "产出"


def test_complete_fact_becomes_a_fact_edge() -> None:
    graph = build_graph(sample_kb())
    fact_edges = [edge for edge in graph.get_edges() if edge.kind == "fact"]

    assert len(fact_edges) == 1
    edge = fact_edges[0]
    assert edge.type == "输出"
    assert edge.metadata["statements"] == ["解析器输出文档模型"]
    assert edge.metadata["sources"][0].quote == "解析器输出文档模型"


def test_incomplete_fact_stays_unlinked() -> None:
    kb = make_kb(
        entities=(entity("解析器"), entity("文档模型")),
        facts=(
            fact("解析器很重要", subject="解析器"),
            fact("没有主语的事实", predicate="related to", object="文档模型"),
        ),
    )

    graph = build_graph(kb)

    assert graph.get_edges() == []
    assert len(graph.unlinked_facts) == 2
    assert any("no complete" in warning for warning in graph.metadata["warnings"])


def test_fact_with_unknown_endpoint_stays_unlinked() -> None:
    kb = make_kb(
        entities=(entity("解析器"),),
        facts=(
            fact("解析器使用不存在的组件", subject="解析器", predicate="使用", object="不存在的组件"),
        ),
    )

    graph = build_graph(kb)

    assert graph.get_edges() == []
    assert graph.unlinked_facts[0].statement == "解析器使用不存在的组件"
    assert graph.metadata["unlinked_facts"] == 1


def test_duplicate_nodes_are_merged() -> None:
    first = entity("解析器", description="短", aliases=("Parser",), sources=(src_ref("docA", quote="q1"),))
    second = entity("解析器", description="更长的描述", aliases=("parser core",), sources=(src_ref("docB", quote="q2"),))
    kb = make_kb(entities=(first, second))

    graph = build_graph(kb)

    assert len(graph.get_nodes()) == 1
    node = graph.get_nodes()[0]
    assert node.metadata["description"] == "更长的描述"
    assert set(node.aliases) == {"Parser", "parser core"}
    assert len(node.metadata["sources"]) == 2


def test_duplicate_edges_are_merged() -> None:
    kb = make_kb(
        entities=(entity("解析器"), entity("文档模型")),
        relations=(
            relation("解析器", "文档模型", type="produces", sources=(src_ref("docA", quote="q1"),)),
            relation("解析器", "文档模型", type="Produces", sources=(src_ref("docB", quote="q2"),)),
        ),
    )

    graph = build_graph(kb)

    assert len(graph.get_edges()) == 1
    edge = graph.get_edges()[0]
    assert [source.quote for source in edge.metadata["sources"]] == ["q1", "q2"]


def test_relation_and_fact_with_the_same_triple_share_one_edge() -> None:
    kb = make_kb(
        entities=(entity("解析器"), entity("文档模型")),
        relations=(
            relation("解析器", "文档模型", type="produces", sources=(src_ref("docA", quote="q1"),)),
        ),
        facts=(
            fact(
                "解析器 produces 文档模型",
                subject="解析器",
                predicate="produces",
                object="文档模型",
                sources=(src_ref("docB", quote="q2"),),
            ),
        ),
    )

    graph = build_graph(kb)

    assert len(graph.get_edges()) == 1
    edge = graph.get_edges()[0]
    assert edge.metadata["kinds"] == ["fact", "relation"]
    assert len(edge.metadata["sources"]) == 2
    assert edge.metadata["statements"] == ["解析器 produces 文档模型"]


def test_dangling_relation_is_kept_unlinked() -> None:
    kb = make_kb(
        entities=(entity("解析器"),),
        relations=(relation("解析器", "不存在的对象", type="uses"),),
    )

    graph = build_graph(kb)

    assert graph.get_edges() == []
    assert graph.unlinked_relations[0].target == "不存在的对象"
    assert graph.metadata["unlinked_relations"] == 1
    assert any("matches no node" in warning for warning in graph.metadata["warnings"])


def test_self_loop_is_allowed_and_counted() -> None:
    kb = make_kb(
        entities=(entity("解析器"),),
        relations=(relation("解析器", "解析器", type="depends on"),),
    )

    graph = build_graph(kb)

    assert len(graph.get_edges()) == 1
    assert graph.get_edges()[0].is_self_loop is True
    assert graph.metadata["self_loops"] == 1


def test_alias_endpoints_resolve_to_the_same_node() -> None:
    kb = make_kb(
        entities=(entity("解析器", aliases=("Parser",)), entity("文档模型")),
        relations=(relation("Parser", "文档模型", type="produces"),),
    )

    graph = build_graph(kb)

    edge = graph.get_edges()[0]
    assert edge.source == "Parser"
    assert edge.metadata["source_id"] == make_knowledge_id("entity", "解析器")


def test_explicit_ids_win_over_name_matching() -> None:
    entity_node = entity("Python", description="实体")
    concept_node = concept("Python", description="概念")
    kb = make_kb(
        entities=(entity_node, entity("文档模型")),
        concepts=(concept_node,),
        relations=(
            relation(
                "Python",
                "文档模型",
                type="uses",
                source_id=concept_node.id,
            ),
        ),
    )

    graph = build_graph(kb)

    edge = graph.get_edges()[0]
    assert edge.metadata["source_id"] == concept_node.id
    assert edge.metadata["ambiguous_source"] is False


def test_same_title_entity_and_concept_are_two_nodes() -> None:
    kb = make_kb(
        entities=(entity("Python", description="实体"),),
        concepts=(concept("Python", description="概念"),),
        relations=(relation("Python", "Python", type="related to"),),
    )

    graph = build_graph(kb)

    assert len(graph.get_nodes()) == 2
    assert {node.kind for node in graph.get_nodes()} == {KIND_ENTITY, KIND_CONCEPT}
    assert len(graph.get_edges()) == 1
    edge = graph.get_edges()[0]
    assert edge.metadata["ambiguous_source"] is True
    assert edge.metadata["ambiguous_target"] is True
    assert "python" in graph.metadata["ambiguous_names"]


def test_empty_knowledge_base_gives_an_empty_graph() -> None:
    graph = build_graph(make_kb())

    assert graph.get_nodes() == []
    assert graph.get_edges() == []
    assert graph.metadata["nodes"] == 0
    assert graph.metadata["edges"] == 0


def test_documents_are_copied() -> None:
    graph = build_graph(sample_kb())

    assert [document["id"] for document in graph.documents] == ["docA", "docB"]


def test_knowledge_base_is_not_modified() -> None:
    kb = sample_kb()
    before = kb.to_dict()

    build_graph(kb)

    assert kb.to_dict() == before


def test_building_twice_is_stable() -> None:
    kb = sample_kb()

    first = build_graph(kb)
    second = build_graph(kb)

    assert json.dumps(first.to_dict(), ensure_ascii=False) == json.dumps(
        second.to_dict(), ensure_ascii=False
    )


def test_building_does_not_depend_on_input_order() -> None:
    kb = sample_kb()
    reordered = make_kb(
        entities=tuple(reversed(kb.entities)),
        concepts=tuple(kb.concepts),
        facts=tuple(kb.facts),
        relations=tuple(kb.relations),
        documents=tuple(kb.documents),
    )

    assert build_graph(kb).to_dict() == build_graph(reordered).to_dict()


def test_sources_reach_the_graph() -> None:
    kb = sample_kb()
    expected = set()
    for collection in (kb.entities, kb.concepts, kb.facts, kb.relations):
        for item in collection:
            for source in item.sources:
                expected.add((source.document_id, source.section_id, source.quote))

    graph = build_graph(kb)
    found = set()
    for node in graph.get_nodes():
        for source in node.metadata["sources"]:
            found.add((source.document_id, source.section_id, source.quote))
    for edge in graph.get_edges():
        for source in edge.metadata["sources"]:
            found.add((source.document_id, source.section_id, source.quote))
    for relation in graph.unlinked_relations:
        for source in relation.sources:
            found.add((source.document_id, source.section_id, source.quote))
    for fact in graph.unlinked_facts:
        for source in fact.sources:
            found.add((source.document_id, source.section_id, source.quote))

    assert expected <= found


def test_rejects_input_that_is_not_a_knowledge_base() -> None:
    with pytest.raises(TypeError) as error:
        build_graph({"entities": []})

    assert "KnowledgeBase" in str(error.value)


def test_metadata_reports_the_build() -> None:
    graph = build_graph(sample_kb())

    assert graph.metadata["nodes"] == 2
    assert graph.metadata["edges"] == 2
    assert graph.metadata["relations"] == 1
    assert graph.metadata["facts"] == 1
    assert graph.metadata["self_loops"] == 0
    assert graph.metadata["builder_version"] == "graph-builder-v1"
