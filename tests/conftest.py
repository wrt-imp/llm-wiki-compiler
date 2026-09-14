"""Shared test fixtures for the parser stage."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def text_file(tmp_path: Path) -> Callable[..., Path]:
    """Return a helper that writes a text file with an explicit encoding."""

    def _write(name: str, text: str, encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        path.write_bytes(text.encode(encoding))
        return path

    return _write


@pytest.fixture
def sample_pdf() -> Path:
    """Two page English PDF with document information metadata."""

    return FIXTURES_DIR / "sample.pdf"


@pytest.fixture
def chinese_pdf() -> Path:
    """Two page Chinese PDF without document information metadata."""

    return FIXTURES_DIR / "chinese.pdf"
