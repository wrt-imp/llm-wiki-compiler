"""Errors raised by the Semantic Merge stage."""

from __future__ import annotations


class MergeError(Exception):
    """Base class for every merge failure."""


class InvalidJudgeResponseError(MergeError):
    """The LLM judge answered, but not with ``{"same": bool, "reason": str}``."""
