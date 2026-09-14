"""Every parser must return the same Document structure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import pytest

from compiler.parser import (
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    FORMAT_TXT,
    Document,
    parse_file,
)

REQUIRED_FIELDS = (
    "id",
    "title",
    "source",
    "format",
    "content",
    "sections",
    "metadata",
)


@pytest.fixture
def all_sources(
    text_file: Callable[..., Path], sample_pdf: Path, chinese_pdf: Path
) -> List[Tuple[Path, str]]:
    return [
        (text_file("contract.txt", "中文与英文 mixed content\n"), FORMAT_TXT),
        (text_file("contract.md", "# Contract\n\nbody\n"), FORMAT_MARKDOWN),
        (sample_pdf, FORMAT_PDF),
        (chinese_pdf, FORMAT_PDF),
    ]


def test_every_parser_returns_complete_document_fields(
    all_sources: List[Tuple[Path, str]]
) -> None:
    for path, expected_format in all_sources:
        document = parse_file(path)

        assert isinstance(document, Document)
        assert set(document.to_dict()) == set(REQUIRED_FIELDS)
        assert document.format == expected_format
        assert document.id and isinstance(document.id, str)
        assert document.title.strip()
        assert document.source == str(path)
        assert document.content.strip()
        assert isinstance(document.sections, List)
        assert isinstance(document.metadata, Dict)


def test_document_ids_are_stable_and_unique(
    all_sources: List[Tuple[Path, str]]
) -> None:
    ids = []
    for path, _ in all_sources:
        first = parse_file(path)
        second = parse_file(path)

        assert first.id == second.id
        assert len(first.id) == 16
        ids.append(first.id)

    assert len(set(ids)) == len(ids)


def test_metadata_is_per_document_and_json_serializable(
    all_sources: List[Tuple[Path, str]]
) -> None:
    documents = [parse_file(path) for path, _ in all_sources]

    for document in documents:
        document.metadata["marker"] = "set by this test"
        json.dumps(document.to_dict())  # must not raise

    # metadata must not be shared between documents
    for document in documents[1:]:
        assert "marker" in document.metadata
    fresh: Dict[str, Any] = parse_file(all_sources[0][0]).metadata
    assert "marker" not in fresh


def test_to_dict_returns_a_copy_of_metadata(
    text_file: Callable[..., Path]
) -> None:
    document = parse_file(text_file("copy.txt", "content\n"))

    snapshot = document.to_dict()
    snapshot["metadata"]["mutated"] = True

    assert "mutated" not in document.metadata
