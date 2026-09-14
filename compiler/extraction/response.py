"""Reading the raw LLM answer as JSON."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from .errors import InvalidResponseError

_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def parse_llm_json(raw: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parse a raw model answer into a JSON object.

    Small deviations are tolerated and reported instead of failing: markdown
    code fences around the JSON, or text before/after it. Anything that is not
    a JSON object raises :class:`InvalidResponseError`.

    Returns:
        The parsed object plus warnings about what had to be cleaned up.
    """

    warnings: List[str] = []
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidResponseError("the LLM returned an empty response")

    text = raw.strip()
    stripped = _FENCE_RE.sub("", text).strip()
    if stripped != text:
        warnings.append("stripped markdown code fence from the LLM response")
        text = stripped

    payload = _loads(text)
    if payload is None:
        candidate = _outermost_object(text)
        if candidate:
            payload = _loads(candidate)
            if payload is not None:
                warnings.append("ignored text around the JSON object")
    if payload is None:
        raise InvalidResponseError(
            "the LLM response is not valid JSON: " + _snippet(text)
        )
    if not isinstance(payload, dict):
        raise InvalidResponseError(
            "the LLM response must be a JSON object, got "
            f"{type(payload).__name__}: {_snippet(text)}"
        )
    return payload, warnings


def _loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _outermost_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _snippet(text: str, limit: int = 200) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return repr(collapsed)
    return repr(collapsed[:limit] + "...")
