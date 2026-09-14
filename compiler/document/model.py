"""The unified document model: what a source is and how it is organized.

This is stage 2 of the LLM Wiki Compiler::

    Source Files -> Parser -> Document Model -> LLM Extraction -> Knowledge IR

The model answers "what is the source material, and how is it structured".
It deliberately says nothing about the knowledge *inside* the material
(entities, relations, summaries, topics, ...) - describing knowledge is the
job of the Knowledge IR, and the two must stay separate.

Nothing in this module depends on a concrete file format, on an LLM, or on the
Knowledge IR. Format specific facts live in ``Document.metadata`` and
``Section.metadata`` as plain data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

FORMAT_PDF = "pdf"
FORMAT_MARKDOWN = "markdown"
FORMAT_TXT = "txt"

#: Formats the parser stage can produce.
SUPPORTED_FORMATS = (FORMAT_MARKDOWN, FORMAT_PDF, FORMAT_TXT)

#: Values of ``Section.metadata["kind"]``. They describe *structure*, never meaning.
SECTION_KIND_HEADING = "heading"
SECTION_KIND_PREAMBLE = "preamble"
SECTION_KIND_PAGE = "page"
SECTION_KIND_DOCUMENT = "document"


def make_document_id(source: str) -> str:
    """Return a stable id derived from a source path.

    The id only depends on the (normalized) path, so parsing the same file
    twice - or from a different process - always yields the same id. That
    keeps later stages able to trace a knowledge unit back to its source.
    """

    normalized = str(source).replace("\\", "/").strip().casefold()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def make_section_id(document_id: str, path: str) -> str:
    """Return a section id from its document id and ordinal path.

    ``path`` is the position of the section inside the document, for example
    ``"2.1"`` for the first child of the second top level section.
    """

    return f"{document_id}#{path}"


@dataclass
class Section:
    """One node of a document's structure.

    Attributes:
        id: ``"<document id>#<ordinal path>"``, stable for a given source.
        title: Heading text. Empty for a markdown preamble, synthesized for
            PDF pages (see ``metadata["kind"]``).
        content: This section's *own* text: no heading line, and no text that
            belongs to nested sections. ``Document.content`` is the full text.
        level: Depth in the section tree, starting at 1 for top level sections.
        children: Nested sub-sections.
        metadata: Where the section came from - ``kind``, ``line_start`` /
            ``line_end`` (1-based line numbers inside ``Document.content``),
            ``page_number`` for PDFs, ``heading_level`` for markdown. Only
            location information belongs here, never extracted knowledge.
    """

    id: str
    title: str
    content: str
    level: int
    children: List["Section"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def walk(self) -> Iterator["Section"]:
        """Yield this section and all descendants, depth first."""

        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, section_id: str) -> Optional["Section"]:
        """Return the descendant (or self) with ``section_id``, if any."""

        for section in self.walk():
            if section.id == section_id:
                return section
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON friendly copy, children included."""

        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "level": self.level,
            "children": [child.to_dict() for child in self.children],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Section":
        """Rebuild a section (and its children) from :meth:`to_dict` output."""

        return cls(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            level=data["level"],
            children=[cls.from_dict(child) for child in data.get("children", [])],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Document:
    """One source file: its normalized text plus how that text is organized.

    Attributes:
        id: Stable identifier derived from the resolved source path.
        title: Best available human readable title for the source.
        source: The path exactly as it was handed to the parser.
        format: ``"pdf"``, ``"markdown"`` or ``"txt"`` - a label only; nothing
            in the model changes behaviour based on it.
        content: The full normalized text, newline normalized to ``\\n``.
        sections: Top level sections of the document, nested via ``children``.
        metadata: Source and parsing facts (encoding, page count, front
            matter, ...). No knowledge extracted from the text.
    """

    id: str
    title: str
    source: str
    format: str
    content: str
    sections: List[Section] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def walk_sections(self) -> Iterator[Section]:
        """Yield every section in document order (depth first)."""

        for section in self.sections:
            yield from section.walk()

    def find_section(self, section_id: str) -> Optional[Section]:
        """Return the section with ``section_id``, if the document has one."""

        for section in self.walk_sections():
            if section.id == section_id:
                return section
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON friendly copy, sections included."""

        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "format": self.format,
            "content": self.content,
            "sections": [section.to_dict() for section in self.sections],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        """Rebuild a document from :meth:`to_dict` output."""

        return cls(
            id=data["id"],
            title=data["title"],
            source=data["source"],
            format=data["format"],
            content=data["content"],
            sections=[
                Section.from_dict(section) for section in data.get("sections", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )
