"""Test support helpers: a scripted mock LLM client and sample payloads.

Imported by the extraction tests as ``from support import ...`` (pytest puts
the ``tests`` directory on ``sys.path``). Nothing here touches the network.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union

Response = Union[str, Exception]


class ScriptedLLMClient:
    """A mock ``LLMClient`` that returns queued answers and records prompts."""

    def __init__(self, *responses: Response, model: str = "mock-model") -> None:
        self._responses: List[Response] = list(responses)
        self.model = model
        self.calls: List[Tuple[str, str]] = []

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("ScriptedLLMClient ran out of scripted responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def last_system_prompt(self) -> str:
        return self.calls[-1][0]

    @property
    def last_user_prompt(self) -> str:
        return self.calls[-1][1]


def source(
    section_id: Optional[str] = None,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> Dict[str, Any]:
    """One ``sources`` entry as the model would emit it."""

    return {"section_id": section_id, "page_number": page_number, "quote": quote}


def sample_payload(
    section_id: Optional[str] = None,
    *,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> Dict[str, Any]:
    """A complete, valid extraction payload with one item of each kind."""

    src = [source(section_id, page_number, quote)]
    return {
        "entities": [
            {
                "name": "解析器",
                "type": "system",
                "description": "把源文件统一成 Document 的组件",
                "aliases": ["Parser"],
                "sources": src,
            }
        ],
        "concepts": [
            {
                "name": "文档模型",
                "description": "解析结果的结构化表示",
                "aliases": [],
                "sources": src,
            }
        ],
        "facts": [
            {
                "statement": "解析器把 PDF、Markdown、TXT 统一成 Document",
                "subject": "解析器",
                "predicate": "输出",
                "object": "Document",
                "sources": src,
            }
        ],
        "relations": [
            {
                "source": "解析器",
                "target": "文档模型",
                "type": "produces",
                "description": "解析器产出文档模型",
                "sources": src,
            }
        ],
    }


def payload_json(
    section_id: Optional[str] = None,
    *,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> str:
    """``sample_payload`` serialized the way a well behaved model would."""

    payload = sample_payload(section_id, page_number=page_number, quote=quote)
    return json.dumps(payload, ensure_ascii=False)


def empty_payload() -> Dict[str, Any]:
    """The answer for a document with no extractable knowledge."""

    return {"entities": [], "concepts": [], "facts": [], "relations": []}
