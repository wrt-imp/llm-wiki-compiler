"""The unified document structure returned by every parser."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict

FORMAT_PDF = "pdf"
FORMAT_MARKDOWN = "markdown"
FORMAT_TXT = "txt"

#: Formats the current parser stage can produce.
SUPPORTED_FORMATS = (FORMAT_MARKDOWN, FORMAT_PDF, FORMAT_TXT)


def make_document_id(source: str) -> str:
    """Return a stable id derived from a source path.

    The id only depends on the (normalized) path, so parsing the same file
    twice - or from a different process - always yields the same id. That
    keeps later stages able to trace a knowledge unit back to its source.
    """

    normalized = str(source).replace("\\", "/").strip().casefold()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Document:
    """One source file, normalized into plain text plus metadata.

    Attributes:
        id: Stable identifier derived from the resolved source path.
        title: Best available human readable title for the source.
        source: The path exactly as it was handed to the parser.
        format: One of :data:`SUPPORTED_FORMATS`.
        content: The extracted plain text, newline normalized to ``\\n``.
        metadata: Format specific extras (for PDFs, for example, the per page
            text used later for source tracing).
    """

    id: str
    title: str
    source: str
    format: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a shallow, JSON friendly copy of the document."""

        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "format": self.format,
            "content": self.content,
            "metadata": dict(self.metadata),
        }
