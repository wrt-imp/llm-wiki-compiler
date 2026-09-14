"""Shared parser contract and helpers."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .document import Document, make_document_id
from .encoding import DecodedText, decode_bytes
from .errors import SourceNotFoundError

PathLike = Union[str, os.PathLike]

#: Titles derived from file content are truncated to keep them readable.
MAX_TITLE_LENGTH = 120


def first_non_empty_line(text: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """Return the first line with visible content, truncated if needed."""

    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:max_length]
    return ""


class BaseParser(ABC):
    """Contract implemented by every single-format parser.

    Subclasses set :attr:`format` and :attr:`extensions` and implement
    :meth:`parse`. All of them must return the same :class:`Document`
    structure, no matter which file format they read.
    """

    #: Value written to ``Document.format``.
    format: str = ""
    #: Lower case file extensions handled by this parser, e.g. ``(".md",)``.
    extensions: tuple[str, ...] = ()

    def supports(self, path: PathLike) -> bool:
        """Return ``True`` when this parser handles ``path``'s extension."""

        return Path(path).suffix.lower() in self.extensions

    @abstractmethod
    def parse(self, path: PathLike) -> Document:
        """Parse ``path`` into a :class:`Document`."""

    # ------------------------------------------------------------------
    # Helpers shared by the concrete parsers
    # ------------------------------------------------------------------
    def _resolve_source(self, path: PathLike) -> Path:
        """Validate the source path and return it as a :class:`Path`."""

        source = Path(path)
        if not source.exists():
            raise SourceNotFoundError(f"source file does not exist: {source}")
        if not source.is_file():
            raise SourceNotFoundError(f"source path is not a file: {source}")
        return source

    def _read_text(self, source: Path, encoding: Optional[str] = None) -> DecodedText:
        """Read ``source`` and decode it, handling UTF-8 / GBK / Big5 / BOMs."""

        return decode_bytes(source.read_bytes(), encoding=encoding)

    def _build_document(
        self,
        source: Path,
        *,
        title: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> Document:
        """Assemble the unified :class:`Document` for this parser."""

        resolved_title = title.strip() or source.stem
        return Document(
            id=make_document_id(str(source.resolve())),
            title=resolved_title,
            source=str(source),
            format=self.format,
            content=content,
            metadata=metadata,
        )
