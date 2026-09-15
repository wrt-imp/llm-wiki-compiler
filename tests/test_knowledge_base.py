"""KnowledgeBase model tests."""

from __future__ import annotations

import json

from compiler.knowledge import Entity, KnowledgeBase
from support import make_ir, src_ref


def sample_base() -> KnowledgeBase:
    return KnowledgeBase(
        entities=[Entity(name="解析器", description="d", sources=[src_ref("docA")])],
        documents=[{"id": "docA", "title": "t", "source": "a.md"}],
        metadata={"judged_pairs": 3},
    )


def test_defaults_and_counts() -> None:
    knowledge_base = KnowledgeBase()

    assert knowledge_base.is_empty() is True
    assert knowledge_base.counts() == {
        "entities": 0,
        "concepts": 0,
        "facts": 0,
        "relations": 0,
    }
    assert knowledge_base.document_ids() == []


def test_counts_and_document_ids() -> None:
    knowledge_base = KnowledgeBase(
        entities=[Entity(name="a"), Entity(name="b")],
        documents=[
            {"id": "docA", "title": "A", "source": "a.md"},
            {"id": "docB", "title": "B", "source": "b.md"},
        ],
    )

    assert knowledge_base.counts()["entities"] == 2
    assert knowledge_base.document_ids() == ["docA", "docB"]
    assert knowledge_base.is_empty() is False


def test_round_trip() -> None:
    knowledge_base = sample_base()

    restored = KnowledgeBase.from_dict(
        json.loads(json.dumps(knowledge_base.to_dict(), ensure_ascii=False))
    )

    assert restored == knowledge_base
    assert restored.entities[0].sources[0].document_id == "docA"
    assert restored.metadata["judged_pairs"] == 3


def test_ir_can_be_used_to_build_documents() -> None:
    ir = make_ir("docA")

    assert ir.document_title == "title of docA"
    assert ir.source == "docA.md"
