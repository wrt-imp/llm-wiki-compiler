"""An OpenAI compatible client (optional; the tests use mocks instead)."""

from __future__ import annotations

import os
from typing import Any, Optional

from .client import LLMError

DEFAULT_MODEL = "gpt-4o-mini"

ENV_API_KEY = "OPENAI_API_KEY"
ENV_BASE_URL = "OPENAI_BASE_URL"
ENV_MODEL = "LLM_MODEL"


class OpenAIChatClient:
    """Chat completions client for OpenAI and compatible gateways.

    Configuration comes from the arguments or from the environment
    (``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, ``LLM_MODEL``). The ``openai``
    package is imported lazily, so the rest of the pipeline - and the whole
    test suite - works without it and without network access.
    """

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        timeout: float = 120.0,
        json_mode: bool = True,
        client: Any = None,
    ) -> None:
        self.model = model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL
        self.temperature = temperature
        self.json_mode = json_mode
        self._api_key = api_key if api_key is not None else os.environ.get(ENV_API_KEY)
        self._base_url = (
            base_url if base_url is not None else os.environ.get(ENV_BASE_URL)
        )
        self._timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **overrides: Any) -> "OpenAIChatClient":
        """Build a client from the environment, with optional overrides."""

        return cls(**overrides)

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Send both prompts and return the raw answer text."""

        client = self._ensure_client()
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }
        if self.json_mode:
            request["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:  # network, auth, rate limit, bad request, ...
            raise LLMError(f"LLM request failed: {exc}") from exc

        content = _first_message_content(response)
        if not content or not content.strip():
            raise LLMError("LLM returned an empty response")
        return content

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMError(
                f"{ENV_API_KEY} is not set; a real LLM call needs an API key"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise LLMError(
                "the 'openai' package is required for OpenAIChatClient"
            ) from exc
        self._client = OpenAI(
            api_key=self._api_key, base_url=self._base_url, timeout=self._timeout
        )
        return self._client


def _first_message_content(response: Any) -> str:
    """Pull the text out of a chat completion response (tolerant)."""

    try:
        choices = response.choices
    except AttributeError:
        return ""
    if not choices:
        return ""
    content = getattr(choices[0].message, "content", None)
    return content if isinstance(content, str) else ""
