"""LLM access for the LLM Wiki Compiler.

The extraction stage depends on the small :class:`~compiler.llm.client.LLMClient`
protocol, so any model can be plugged in::

    >>> from compiler.llm import LLMClient, LLMError, OpenAIChatClient

``OpenAIChatClient`` is the only implementation that talks to a real API; it is
optional and never used by the unit tests.
"""

from .client import LLMClient, LLMError
from .openai_client import DEFAULT_MODEL, OpenAIChatClient

__all__ = [
    "DEFAULT_MODEL",
    "LLMClient",
    "LLMError",
    "OpenAIChatClient",
]
