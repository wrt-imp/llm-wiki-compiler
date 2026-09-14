"""Stage 2 of the LLM Wiki Compiler: the Document Model.

The parser stage turns files into normalized text plus parse metadata; this
stage adds the document structure (sections) on top, so later stages get one
uniform shape for PDF, Markdown and TXT::

    >>> from compiler.document import load_document
    >>> document = load_document("notes.md")
    >>> [(section.title, section.level) for section in document.sections]
    [('', 1), ('Overview', 1), ('Details', 2)]

The model describes *what the source is and how it is organized*. It does not
describe the knowledge inside it - that is the Knowledge IR's job, and it is
not implemented yet.
"""

from .builder import attach_sections, build_sections, load_document
from .model import (
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    FORMAT_TXT,
    SECTION_KIND_DOCUMENT,
    SECTION_KIND_HEADING,
    SECTION_KIND_PAGE,
    SECTION_KIND_PREAMBLE,
    SUPPORTED_FORMATS,
    Document,
    Section,
    make_document_id,
    make_section_id,
)

__all__ = [
    "Document",
    "FORMAT_MARKDOWN",
    "FORMAT_PDF",
    "FORMAT_TXT",
    "SECTION_KIND_DOCUMENT",
    "SECTION_KIND_HEADING",
    "SECTION_KIND_PAGE",
    "SECTION_KIND_PREAMBLE",
    "SUPPORTED_FORMATS",
    "Section",
    "attach_sections",
    "build_sections",
    "load_document",
    "make_document_id",
    "make_section_id",
]
