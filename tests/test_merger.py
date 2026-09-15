"""Semantic Merge tests: the required scenarios plus provenance checks."""

from __future__ import annotations

import json
from typing import Any, Set, Tuple

import pytest

from compiler.extraction import InvalidResponseError
from compiler.knowledge import KnowledgeBase, make_knowledge_id
from compiler.llm import LLMError
from compiler.merge import (
    InvalidJudgeResponseError,
    JudgeVerdict,
    LLMJudge,
    Merger,
    merge_knowledge_bases,
)
from support import (
    ScriptedJudge,
    ScriptedLLMClient,
    concept,
    entity,
    fact,
    make_ir,
    relation,
    src_ref,
)

SourceKey = Tuple[str, str, None, str]


def all_sources(items: Any) -> Set[tuple]:
    """Every source reference of every item, as comparable tuples."""

    result = set()
    for collection in (items.entities, items.concepts, items.facts, items.relations):
        for item in collection:
            for ref in item.sources:
                result.add(
                    (ref.document_id, ref.section_id, ref.page_number, ref.quote)
                )
    return result


def ir_pair_with_alias_bridge():
    """Two IRs whose entities are the same object via a shared alias."""

    left = make_ir(
        "docA",
        entities=(
            entity(
                "解析器",
                type="system",
                description="把源文件统一成 Document 的组件",
                aliases=("Parser",),
                sources=(src_ref("docA", section_id="docA#1", quote="q1"),),
            ),
        ),
    )
    right = make_ir(
        "docB",
        entities=(
            entity(
                "Parser",
                description="converts sources into documents",
                sources=(src_ref("docB", section_id="docB#1", quote="q2"),),
            ),
        ),
    )
    return left, right


# ----------------------------------------------------------------------
# 1 - 5: entities and concepts
# ----------------------------------------------------------------------
def test_identical_entities_merge_without_asking_the_llm() -> None:
    left = make_ir("docA", entities=(entity("解析器", sources=(src_ref("docA", quote="q1"),)),))
    right = make_ir("docB", entities=(entity("解析器", sources=(src_ref("docB", quote="q2"),)),))
    judge = ScriptedJudge()

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 1
    assert judge.calls == []
    assert knowledge_base.metadata["judged_pairs"] == 0
    assert knowledge_base.metadata["merges"][0]["method"] == "normalized-name"
    assert {ref.quote for ref in knowledge_base.entities[0].sources} == {"q1", "q2"}


def test_case_and_space_differences_merge_without_the_llm() -> None:
    left = make_ir("docA", entities=(entity("  Parser ", sources=(src_ref("docA", quote="q1"),)),))
    right = make_ir("docB", entities=(entity("parser", sources=(src_ref("docB", quote="q2"),)),))
    judge = ScriptedJudge()

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 1
    assert knowledge_base.entities[0].name == "Parser"
    assert judge.calls == []


def test_clearly_different_entities_are_not_merged() -> None:
    left = make_ir("docA", entities=(entity("解析器", sources=(src_ref("docA", quote="q1"),)),))
    right = make_ir("docB", entities=(entity("文档模型", sources=(src_ref("docB", quote="q2"),)),))
    judge = ScriptedJudge()

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert [item.name for item in knowledge_base.entities] == ["解析器", "文档模型"]
    assert judge.calls == []
    assert knowledge_base.metadata["merges"] == []


def test_semantically_equal_entities_with_different_names_are_merged() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = ScriptedJudge(JudgeVerdict(True, "同一个组件"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 1
    assert judge.calls == [("entity", "解析器", "Parser")]
    merged = knowledge_base.entities[0]
    assert merged.name == "解析器"
    assert merged.aliases == ["Parser"]
    assert merged.type == "system"
    assert merged.description == "把源文件统一成 Document 的组件\nconverts sources into documents"
    assert {ref.quote for ref in merged.sources} == {"q1", "q2"}
    assert knowledge_base.metadata["merges"][0]["method"] == "llm"
    assert knowledge_base.metadata["merges"][0]["reasons"] == ["同一个组件"]
    assert knowledge_base.metadata["judged_same"] == 1


def test_concepts_are_merged_the_same_way() -> None:
    left = make_ir(
        "docA",
        concepts=(
            concept(
                "知识图谱",
                aliases=("Knowledge Graph",),
                sources=(src_ref("docA", quote="q1"),),
            ),
        ),
    )
    right = make_ir(
        "docB",
        concepts=(concept("Knowledge Graph", sources=(src_ref("docB", quote="q2"),)),),
    )
    judge = ScriptedJudge(JudgeVerdict(True, "同一概念"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.concepts) == 1
    assert judge.calls == [("concept", "知识图谱", "Knowledge Graph")]
    assert knowledge_base.concepts[0].name == "知识图谱"
    assert knowledge_base.concepts[0].aliases == ["Knowledge Graph"]


def test_canonical_name_prefers_the_most_common_spelling() -> None:
    left = make_ir(
        "docA",
        entities=(
            entity("解析器", sources=(src_ref("docA", quote="q1"),)),
            entity("解析器", sources=(src_ref("docA", quote="q2"),)),
        ),
    )
    right = make_ir(
        "docB",
        entities=(
            entity(
                "Parser",
                aliases=("解析器",),
                sources=(src_ref("docB", quote="q3"),),
            ),
        ),
    )
    judge = ScriptedJudge(JudgeVerdict(True, "same object"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 1
    assert knowledge_base.entities[0].name == "解析器"
    assert knowledge_base.entities[0].aliases == ["Parser"]
    # both candidate pairs share one memo entry, so only one model call happens
    assert len(judge.calls) == 1


def test_entity_type_prefers_the_specific_one() -> None:
    left = make_ir("docA", entities=(entity("Parser", type="other", sources=(src_ref("docA"),)),))
    right = make_ir("docB", entities=(entity("parser", type="system", sources=(src_ref("docB"),)),))

    knowledge_base = merge_knowledge_bases([left, right], None)

    assert len(knowledge_base.entities) == 1
    assert knowledge_base.entities[0].type == "system"


# ----------------------------------------------------------------------
# 6 - 8: facts, relations and provenance
# ----------------------------------------------------------------------
def test_duplicate_facts_are_deduplicated() -> None:
    left = make_ir(
        "docA",
        facts=(
            fact(
                "解析器把 PDF、Markdown、TXT 统一成 Document。",
                subject="解析器",
                object="Document",
                sources=(src_ref("docA", quote="q1"),),
            ),
        ),
    )
    right = make_ir(
        "docB",
        facts=(
            fact(
                "解析器把 PDF、Markdown、TXT 统一成 Document",
                subject="解析器",
                object="Document",
                sources=(src_ref("docB", quote="q2"),),
            ),
        ),
    )

    knowledge_base = merge_knowledge_bases([left, right], None)

    assert len(knowledge_base.facts) == 1
    assert {ref.quote for ref in knowledge_base.facts[0].sources} == {"q1", "q2"}
    assert knowledge_base.facts[0].statement.endswith("Document。")


def test_duplicate_relations_are_deduplicated() -> None:
    left = make_ir(
        "docA",
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="produces",
                description="解析器产出文档模型",
                sources=(src_ref("docA", quote="q1"),),
            ),
        ),
    )
    right = make_ir(
        "docB",
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="Produces",
                sources=(src_ref("docB", quote="q2"),),
            ),
        ),
    )

    knowledge_base = merge_knowledge_bases([left, right], None)

    assert len(knowledge_base.relations) == 1
    assert {ref.quote for ref in knowledge_base.relations[0].sources} == {"q1", "q2"}
    assert knowledge_base.relations[0].description == "解析器产出文档模型"


def test_sources_are_never_lost() -> None:
    left = make_ir(
        "docA",
        entities=(
            entity("解析器", aliases=("Parser",), sources=(src_ref("docA", quote="q1"),)),
        ),
        concepts=(concept("文档模型", sources=(src_ref("docA", quote="q2"),)),),
        facts=(fact("解析器输出 Document", sources=(src_ref("docA", quote="q3"),)),),
        relations=(
            relation(
                "解析器", "文档模型", type="produces", sources=(src_ref("docA", quote="q4"),)
            ),
        ),
    )
    right = make_ir(
        "docB",
        entities=(
            entity("Parser", aliases=("解析器",), sources=(src_ref("docB", quote="q5"),)),
        ),
        concepts=(concept("文档模型 ", sources=(src_ref("docB", quote="q6"),)),),
        facts=(fact("解析器输出 Document。", sources=(src_ref("docB", quote="q7"),)),),
        relations=(
            relation(
                "Parser", "文档模型", type="produces", sources=(src_ref("docB", quote="q8"),)
            ),
        ),
    )
    judge = ScriptedJudge(JudgeVerdict(True, "same component"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert all_sources(knowledge_base) >= all_sources(left) | all_sources(right)
    assert len(knowledge_base.entities) == 1
    assert len(knowledge_base.concepts) == 1
    assert len(knowledge_base.facts) == 1
    assert len(knowledge_base.relations) == 1


def test_fact_endpoints_are_canonicalized() -> None:
    left, right = ir_pair_with_alias_bridge()
    right.facts.append(
        fact(
            "Parser converts sources into documents",
            subject="Parser",
            object="Document",
            sources=[src_ref("docB", quote="q3")],
        )
    )
    judge = ScriptedJudge(JudgeVerdict(True, "same component"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert knowledge_base.facts[0].subject == "解析器"
    assert knowledge_base.facts[0].object == "Document"
    assert knowledge_base.facts[0].statement == "Parser converts sources into documents"


def test_relation_endpoints_point_at_the_merged_ids() -> None:
    left, right = ir_pair_with_alias_bridge()
    left.relations.append(
        relation("解析器", "文档模型", type="produces", sources=[src_ref("docA", quote="q3")])
    )
    right.relations.append(
        relation(
            "Parser",
            "文档模型",
            type="produces",
            source_id=right.entities[0].id,
            sources=[src_ref("docB", quote="q4")],
        )
    )
    judge = ScriptedJudge(JudgeVerdict(True, "same component"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    merged_entity = knowledge_base.entities[0]
    assert len(knowledge_base.relations) == 1
    relation_out = knowledge_base.relations[0]
    assert relation_out.source == "解析器"
    assert relation_out.source_id == merged_entity.id
    assert relation_out.source_id == make_knowledge_id("entity", "解析器")
    assert relation_out.target_id is None


def test_three_knowledge_irs_merge_transitively() -> None:
    first = make_ir(
        "docA",
        entities=(
            entity("解析器", aliases=("Parser",), sources=(src_ref("docA", quote="q1"),)),
        ),
    )
    second = make_ir(
        "docB",
        entities=(
            entity("Parser", aliases=("Parser Tool",), sources=(src_ref("docB", quote="q2"),)),
        ),
    )
    third = make_ir(
        "docC",
        entities=(entity("Parser Tool", sources=(src_ref("docC", quote="q3"),)),),
    )
    judge = ScriptedJudge(
        JudgeVerdict(True, "same component"), JudgeVerdict(True, "same component")
    )

    knowledge_base = merge_knowledge_bases([first, second, third], judge)

    assert len(knowledge_base.entities) == 1
    assert len(judge.calls) == 2
    assert knowledge_base.document_ids() == ["docA", "docB", "docC"]
    assert len(knowledge_base.entities[0].sources) == 3
    assert set(knowledge_base.entities[0].aliases) == {"Parser", "Parser Tool"}
    assert knowledge_base.metadata["documents"] == 3


# ----------------------------------------------------------------------
# 9 - 12: judge failures, empty input, audit trail
# ----------------------------------------------------------------------
def test_invalid_judge_json_is_reported_and_nothing_is_merged() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = LLMJudge(ScriptedLLMClient("I think they are the same, sorry."))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 2
    assert any(
        "not valid JSON" in failure
        for failure in knowledge_base.metadata["judge_failures"]
    )
    assert any("judge failed" in warning for warning in knowledge_base.metadata["warnings"])
    assert all_sources(knowledge_base) >= all_sources(left) | all_sources(right)


def test_invalid_judge_json_can_be_fatal() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = LLMJudge(ScriptedLLMClient("no json here"))

    with pytest.raises(InvalidResponseError):
        merge_knowledge_bases([left, right], judge, on_judge_error="raise")


def test_judge_contract_violation_is_reported() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = LLMJudge(ScriptedLLMClient('{"reason": "same?"}'))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 2
    assert any(
        "'same'" in failure for failure in knowledge_base.metadata["judge_failures"]
    )


def test_llm_errors_are_reported_without_losing_data() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = LLMJudge(ScriptedLLMClient(LLMError("rate limited")))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert len(knowledge_base.entities) == 2
    assert any(
        "rate limited" in failure
        for failure in knowledge_base.metadata["judge_failures"]
    )


def test_judge_returning_same_false_keeps_both_items() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = ScriptedJudge(JudgeVerdict(False, "只是相关，不是同一个对象"))

    knowledge_base = merge_knowledge_bases([left, right], judge)

    assert [item.name for item in knowledge_base.entities] == ["解析器", "Parser"]
    assert len(judge.calls) == 1
    assert knowledge_base.metadata["judged_same"] == 0
    assert knowledge_base.metadata["merges"] == []
    assert all_sources(knowledge_base) >= all_sources(left) | all_sources(right)


def test_empty_input_produces_an_empty_knowledge_base() -> None:
    empty = merge_knowledge_bases([], None)
    only_empty_ir = merge_knowledge_bases([make_ir("docA")], None)

    assert empty.is_empty() is True
    assert empty.counts() == {
        "entities": 0,
        "concepts": 0,
        "facts": 0,
        "relations": 0,
    }
    assert only_empty_ir.is_empty() is True
    assert only_empty_ir.document_ids() == ["docA"]


def test_metadata_describes_the_run() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = LLMJudge(ScriptedLLMClient('{"same": true, "reason": "same"}'))

    knowledge_base = merge_knowledge_bases([left, right], judge)
    metadata = knowledge_base.metadata

    assert metadata["input_knowledge_irs"] == 2
    assert metadata["judged_pairs"] == 1
    assert metadata["judged_same"] == 1
    assert metadata["judge_model"] == "mock-model"
    assert metadata["judge_prompt_version"] == "merge-judge-v1"
    assert metadata["counts"]["entities"] == 1
    assert metadata["warnings"] == []


def test_without_a_judge_only_normalized_names_merge() -> None:
    left, right = ir_pair_with_alias_bridge()

    knowledge_base = merge_knowledge_bases([left, right], None)

    assert len(knowledge_base.entities) == 2
    assert knowledge_base.metadata["judge_model"] is None
    assert any(
        "no judge configured" in warning
        for warning in knowledge_base.metadata["warnings"]
    )


def test_merged_knowledge_base_round_trips() -> None:
    left, right = ir_pair_with_alias_bridge()
    judge = ScriptedJudge(JudgeVerdict(True, "same"))

    knowledge_base = merge_knowledge_bases([left, right], judge)
    restored = KnowledgeBase.from_dict(
        json.loads(json.dumps(knowledge_base.to_dict(), ensure_ascii=False))
    )

    assert restored == knowledge_base


def test_input_irs_are_not_mutated() -> None:
    left, right = ir_pair_with_alias_bridge()
    before = (all_sources(left), all_sources(right), left.entities[0].name)

    merge_knowledge_bases([left, right], ScriptedJudge(JudgeVerdict(True, "same")))

    assert (all_sources(left), all_sources(right), left.entities[0].name) == before
    assert left.entities[0].aliases == ["Parser"]


def test_invalid_on_judge_error_is_rejected() -> None:
    with pytest.raises(ValueError):
        Merger(None, on_judge_error="explode")


def test_max_judgements_caps_the_model_calls() -> None:
    left = make_ir(
        "docA",
        entities=(entity("parser", sources=(src_ref("docA"),)),),
    )
    right = make_ir(
        "docB",
        entities=(
            entity("parsers", sources=(src_ref("docB"),)),
            entity("parseer", sources=(src_ref("docB"),)),
        ),
    )
    judge = ScriptedJudge(JudgeVerdict(False, "not the same"))

    knowledge_base = merge_knowledge_bases(
        [left, right], judge, max_judgements=1
    )

    assert len(judge.calls) == 1
    assert any(
        "truncated to 1" in warning for warning in knowledge_base.metadata["warnings"]
    )
