"""OpenAIChatClient tests using a fake transport (no network, no API key)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

from compiler.llm import DEFAULT_MODEL, OpenAIChatClient
from compiler.llm.client import LLMError


def fake_transport(
    content: Any = '{"entities": []}', error: Exception = None
) -> Tuple[Any, List[Dict[str, Any]]]:
    """A stand in for the openai client that records the request it got."""

    calls: List[Dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if error is not None:
            raise error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    transport = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return transport, calls


def test_complete_returns_the_message_content() -> None:
    transport, calls = fake_transport('{"entities": []}')
    client = OpenAIChatClient(client=transport, model="test-model")

    answer = client.complete(system_prompt="sys", user_prompt="user")

    assert answer == '{"entities": []}'
    assert calls[0]["model"] == "test-model"
    assert calls[0]["messages"][0] == {"role": "system", "content": "sys"}
    assert calls[0]["messages"][1] == {"role": "user", "content": "user"}
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_json_mode_can_be_disabled() -> None:
    transport, calls = fake_transport()
    client = OpenAIChatClient(client=transport, json_mode=False)

    client.complete(system_prompt="sys", user_prompt="user")

    assert "response_format" not in calls[0]


def test_missing_api_key_raises_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIChatClient()

    with pytest.raises(LLMError) as error:
        client.complete(system_prompt="sys", user_prompt="user")

    assert "OPENAI_API_KEY" in str(error.value)


def test_transport_errors_are_wrapped() -> None:
    transport, _ = fake_transport(error=RuntimeError("boom"))
    client = OpenAIChatClient(client=transport, api_key="test-key")

    with pytest.raises(LLMError) as error:
        client.complete(system_prompt="sys", user_prompt="user")

    assert "boom" in str(error.value)


def test_empty_content_raises_llm_error() -> None:
    transport, _ = fake_transport(content="")
    client = OpenAIChatClient(client=transport, api_key="test-key")

    with pytest.raises(LLMError) as error:
        client.complete(system_prompt="sys", user_prompt="user")

    assert "empty" in str(error.value)


def test_model_defaults_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert OpenAIChatClient().model == DEFAULT_MODEL

    monkeypatch.setenv("LLM_MODEL", "my-local-model")
    assert OpenAIChatClient().model == "my-local-model"
