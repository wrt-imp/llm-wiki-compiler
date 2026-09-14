"""Stage 3 of the LLM Wiki Compiler: LLM extraction.

Turns one Document into a Knowledge IR::

    Document -> Prompt -> LLM -> JSON -> Validation -> Knowledge IR

    >>> from compiler.document import load_document
    >>> from compiler.extraction import extract_knowledge
    >>> knowledge = extract_knowledge(load_document("notes.md"), client)

The LLM only proposes knowledge as JSON; validation decides what enters the IR.
Wiki generation, semantic merge, linking, search, graph and lint are not
implemented yet.
"""

from .errors import ExtractionError, InvalidPayloadError, InvalidResponseError
from .extractor import Extractor, PromptBuilder, extract_knowledge
from .prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_extraction_prompt,
    build_user_prompt,
)
from .response import parse_llm_json
from .validator import REQUIRED_KEYS, validate_payload

__all__ = [
    "ExtractionError",
    "Extractor",
    "InvalidPayloadError",
    "InvalidResponseError",
    "PROMPT_VERSION",
    "PromptBuilder",
    "REQUIRED_KEYS",
    "SYSTEM_PROMPT",
    "build_extraction_prompt",
    "build_user_prompt",
    "extract_knowledge",
    "parse_llm_json",
    "validate_payload",
]
