"""Knowledge IR model tests."""

from __future__ import annotations

import json

from compiler.knowledge import (
    ENTITY_TYPE_OTHER,
    Concept,
    Entity,
    Fact,
    KnowledgeIR,
    Relation,
    SourceRef,
    make_knowledge_id,
    normalize_name,
)


def sample_ir() -> KnowledgeIR:
    source = SourceRef(
        document_id="doc1", section_id="doc1#2", page_number=3, quote="原文"
    )
    return KnowledgeIR(
        document_id="doc1",
        document_title="解析器设计笔记",
        source="notes.md",
        entities=[
            Entity(
                name="解析器",
                type="system",
                description="统一源文件的组件",
                aliases=["Parser"],
                sources=[source],
            )
        ],
        concepts=[Concept(name="文档模型", description="结构化表示", sources=[source])],
        facts=[
            Fact(
                statement="解析器输出 Document",
                subject="解析器",
                predicate="输出",
                object="Document",
                sources=[source],
            )
        ],
        relations=[
            Relation(
                source="解析器",
                target="文档模型",
                type="produces",
                description="产出",
                source_id="e1",
                target_id="c1",
                sources=[source],
            )
        ],
        metadata={"model": "mock-model"},
    )


def test_ids_are_derived_from_names() -> None:
    assert Entity(name="Parser").id == make_knowledge_id("entity", "Parser")
    assert Concept(name="文档模型").id == make_knowledge_id("concept", "文档模型")
    assert Fact(statement="a fact").id == make_knowledge_id("fact", "a fact")
    assert (
        Relation(source="a", target="b", type="uses").id
        == make_knowledge_id("relation", "a|uses|b")
    )


def test_ids_ignore_case_and_extra_spaces() -> None:
    assert Entity(name="Document  Model").id == Entity(name="document model").id
    assert normalize_name("  Document  Model ") == "document model"


def test_item_defaults() -> None:
    entity = Entity(name="x")

    assert entity.type == ENTITY_TYPE_OTHER
    assert entity.aliases == []
    assert entity.sources == []
    assert entity.description == ""


def test_source_ref_round_trip() -> None:
    source = SourceRef(
        document_id="doc", section_id="doc#1", page_number=2, quote="q"
    )

    assert SourceRef.from_dict(source.to_dict()) == source
    assert source.to_dict()["document_id"] == "doc"


def test_knowledge_ir_round_trip() -> None:
    knowledge = sample_ir()

    restored = KnowledgeIR.from_dict(json.loads(json.dumps(knowledge.to_dict())))

    assert restored == knowledge
    assert restored.relations[0].source_id == "e1"
    assert restored.entities[0].sources[0].section_id == "doc1#2"


def test_counts_and_is_empty() -> None:
    knowledge = sample_ir()

    assert knowledge.counts() == {
        "entities": 1,
        "concepts": 1,
        "facts": 1,
        "relations": 1,
    }
    assert knowledge.is_empty() is False
    assert KnowledgeIR(document_id="doc").is_empty() is True
