"""Judge tests: prompt shape, JSON contract, failures (mock client only)."""

from __future__ import annotations

import pytest

from compiler.extraction import InvalidResponseError
from compiler.merge import (
    JUDGE_PROMPT_VERSION,
    InvalidJudgeResponseError,
    LLMJudge,
    build_judge_prompt,
    verdict_from_payload,
)
from support import ScriptedLLMClient, entity, src_ref


def test_verdict_from_payload() -> None:
    assert verdict_from_payload({"same": True, "reason": "same"}).same is True
    assert verdict_from_payload({"same": False, "reason": "no"}).same is False


def test_verdict_tolerates_string_booleans() -> None:
    assert verdict_from_payload({"same": "true"}).same is True
    assert verdict_from_payload({"same": " FALSE "}).same is False


def test_verdict_without_reason_is_accepted() -> None:
    assert verdict_from_payload({"same": True}).reason == ""


def test_missing_same_is_rejected() -> None:
    with pytest.raises(InvalidJudgeResponseError) as error:
        verdict_from_payload({"reason": "looks the same"})

    assert "'same'" in str(error.value)


def test_non_boolean_same_is_rejected() -> None:
    with pytest.raises(InvalidJudgeResponseError):
        verdict_from_payload({"same": 1})


def test_non_string_reason_is_rejected() -> None:
    with pytest.raises(InvalidJudgeResponseError):
        verdict_from_payload({"same": True, "reason": {"why": "because"}})


def test_non_object_payload_is_rejected() -> None:
    with pytest.raises(InvalidJudgeResponseError):
        verdict_from_payload(["same"])


def test_judge_reads_the_client_answer() -> None:
    client = ScriptedLLMClient('{"same": true, "reason": "同一个组件"}')
    judge = LLMJudge(client)

    verdict = judge.judge("entity", entity("解析器"), entity("Parser"))

    assert verdict.same is True
    assert verdict.reason == "同一个组件"
    assert judge.calls == 1


def test_judge_accepts_a_fenced_answer() -> None:
    client = ScriptedLLMClient('```json\n{"same": false, "reason": "different"}\n```')

    verdict = LLMJudge(client).judge("concept", entity("a"), entity("b"))

    assert verdict.same is False


def test_judge_rejects_invalid_json() -> None:
    client = ScriptedLLMClient("They look the same to me!")

    with pytest.raises(InvalidResponseError):
        LLMJudge(client).judge("entity", entity("a"), entity("b"))


def test_prompt_contains_both_items_and_their_evidence() -> None:
    left = entity(
        "解析器",
        type="system",
        description="把源文件统一成 Document",
        aliases=("Parser",),
        sources=(src_ref("docA", section_id="docA#1", quote="解析器把 PDF 统一成 Document"),),
    )
    right = entity("Parser", description="converts sources", sources=(src_ref("docB"),))

    system_prompt, user_prompt = build_judge_prompt("entity", left, right)

    assert '"same"' in system_prompt
    assert "no markdown" in system_prompt.lower()
    assert "Kind: entity" in user_prompt
    assert "name: 解析器" in user_prompt
    assert "name: Parser" in user_prompt
    assert "aliases: Parser" in user_prompt
    assert "document docA" in user_prompt
    assert "解析器把 PDF 统一成 Document" in user_prompt
    assert "do Item A and Item B denote the same entity?" in user_prompt


def test_prompt_version_is_exposed() -> None:
    judge = LLMJudge(ScriptedLLMClient("{}"))

    assert judge.prompt_version == JUDGE_PROMPT_VERSION
