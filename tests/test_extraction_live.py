"""Optional integration test against a real model.

Skipped unless ``OPENAI_API_KEY`` is set, so the normal test run stays offline
and deterministic::

    OPENAI_API_KEY=... LLM_MODEL=gpt-4o-mini python -m pytest tests/test_extraction_live.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from compiler.document import load_document
from compiler.extraction import extract_knowledge
from compiler.knowledge import KnowledgeIR

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY is not set",
)


def test_live_extraction_returns_a_knowledge_ir(chinese_pdf: Path) -> None:
    pytest.importorskip("openai")
    from compiler.llm import OpenAIChatClient

    document = load_document(chinese_pdf)

    knowledge = extract_knowledge(document, OpenAIChatClient())

    assert isinstance(knowledge, KnowledgeIR)
    assert knowledge.document_id == document.id
    for item in [*knowledge.entities, *knowledge.concepts]:
        for ref in item.sources:
            assert ref.document_id == document.id
