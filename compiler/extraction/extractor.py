"""Document -> Prompt -> LLM -> JSON -> Validation -> Knowledge IR."""

from __future__ import annotations

from typing import Callable, Tuple

from ..document import Document
from ..knowledge import KnowledgeIR
from ..llm import LLMClient
from .prompt import PROMPT_VERSION, build_extraction_prompt
from .response import parse_llm_json
from .validator import validate_payload

#: A prompt builder maps a document to ``(system_prompt, user_prompt)``.
PromptBuilder = Callable[[Document], Tuple[str, str]]


class Extractor:
    """Extract a Knowledge IR from one Document using an injected LLM client.

    The client is the only thing that knows about a model API, so swapping the
    model (or injecting a mock in tests) does not touch this class.
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        prompt_builder: PromptBuilder = build_extraction_prompt,
    ) -> None:
        self.client = client
        self.prompt_builder = prompt_builder

    def extract(self, document: Document) -> KnowledgeIR:
        """Extract knowledge from ``document``.

        Args:
            document: A document produced by the Document Model stage. Raw
                paths, file handles and plain strings are rejected on purpose:
                extraction always runs on the Document Model.

        Raises:
            TypeError: when ``document`` is not a Document Model object.
            LLMError: when the model call fails.
            InvalidResponseError: when the answer is not a JSON object.
            InvalidPayloadError: when the JSON breaks the extraction contract.
        """

        if not isinstance(document, Document):
            raise TypeError(
                "Extractor expects a Document Model object, got "
                f"{type(document).__name__}"
            )

        system_prompt, user_prompt = self.prompt_builder(document)
        raw_response = self.client.complete(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        payload, parse_warnings = parse_llm_json(raw_response)
        knowledge, validation_warnings = validate_payload(payload, document)

        knowledge.metadata.update(
            {
                "model": getattr(self.client, "model", None)
                or type(self.client).__name__,
                "prompt_version": PROMPT_VERSION,
                "warnings": [*parse_warnings, *validation_warnings],
                "counts": knowledge.counts(),
            }
        )
        return knowledge


def extract_knowledge(
    document: Document,
    client: LLMClient,
    *,
    prompt_builder: PromptBuilder = build_extraction_prompt,
) -> KnowledgeIR:
    """Convenience wrapper around :class:`Extractor`."""

    return Extractor(client, prompt_builder=prompt_builder).extract(document)
