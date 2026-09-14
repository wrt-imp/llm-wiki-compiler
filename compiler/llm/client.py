"""The LLM boundary: extraction code never talks to an API directly.

Any object with a ``complete`` method is a valid client, so the model can be
swapped (OpenAI, a local model, a mock in tests) without touching the
extraction logic::

    LLMClient -> Extractor
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Raised when a completion cannot be produced."""


@runtime_checkable
class LLMClient(Protocol):
    """Prompts in, raw model output out."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return the model's raw text answer for the two prompts."""
        ...  # pragma: no cover - protocol definition
