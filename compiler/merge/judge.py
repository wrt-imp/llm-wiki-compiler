"""The semantic judge: does this candidate pair denote one knowledge object?"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..extraction.response import parse_llm_json
from ..llm import LLMClient
from .errors import InvalidJudgeResponseError
from .prompt import JUDGE_PROMPT_VERSION, build_judge_prompt


@dataclass(frozen=True)
class JudgeVerdict:
    """What the judge decided about one pair."""

    same: bool
    reason: str = ""


@runtime_checkable
class SemanticJudge(Protocol):
    """Anything that can decide whether two items are the same object."""

    def judge(self, kind: str, left: Any, right: Any) -> JudgeVerdict:
        ...  # pragma: no cover - protocol definition


class LLMJudge:
    """Ask a model about one pair of items at a time.

    The client is injected, so tests use a mock and never touch the network.
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        prompt_version: str = JUDGE_PROMPT_VERSION,
    ) -> None:
        self.client = client
        self.prompt_version = prompt_version
        self.calls = 0

    def judge(self, kind: str, left: Any, right: Any) -> JudgeVerdict:
        system_prompt, user_prompt = build_judge_prompt(kind, left, right)
        raw_response = self.client.complete(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        self.calls += 1
        payload, _warnings = parse_llm_json(raw_response)
        return verdict_from_payload(payload)


def verdict_from_payload(payload: Any) -> JudgeVerdict:
    """Validate ``{"same": bool, "reason": str}`` and return the verdict.

    Raises:
        InvalidJudgeResponseError: when the answer breaks the judge contract.
    """

    if not isinstance(payload, dict):
        raise InvalidJudgeResponseError(
            f"judge response must be a JSON object, got {type(payload).__name__}"
        )
    if "same" not in payload:
        raise InvalidJudgeResponseError(
            "judge response is missing the 'same' field"
        )

    same = payload["same"]
    if isinstance(same, bool):
        pass
    elif isinstance(same, str) and same.strip().casefold() in {"true", "false"}:
        same = same.strip().casefold() == "true"
    else:
        raise InvalidJudgeResponseError(
            "judge response field 'same' must be a boolean"
        )

    reason = payload.get("reason", "")
    if reason is None:
        reason = ""
    if not isinstance(reason, str):
        raise InvalidJudgeResponseError(
            "judge response field 'reason' must be a string"
        )
    return JudgeVerdict(same=same, reason=reason.strip())
