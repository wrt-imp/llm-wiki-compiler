"""Stage 1 of the LLM Wiki Compiler: Parser.

Turns PDF / Markdown / TXT files into one unified :class:`Document` structure:

    >>> from compiler.parser import parse_file
    >>> document = parse_file("notes.md")
    >>> document.format
    'markdown'

Nothing outside this package is part of the parser stage.
"""

from .base import BaseParser, first_non_empty_line
from .document import (
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    FORMAT_TXT,
    SUPPORTED_FORMATS,
    Document,
    make_document_id,
)
from .encoding import DecodedText, decode_bytes, normalize_newlines
from .errors import ParserError, SourceNotFoundError, UnsupportedFormatError
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .registry import (
    ParserRegistry,
    create_default_registry,
    parse_file,
    registry,
)
from .txt_parser import TxtParser

__all__ = [
    "BaseParser",
    "DecodedText",
    "Document",
    "FORMAT_MARKDOWN",
    "FORMAT_PDF",
    "FORMAT_TXT",
    "MarkdownParser",
    "ParserError",
    "ParserRegistry",
    "PdfParser",
    "SUPPORTED_FORMATS",
    "SourceNotFoundError",
    "TxtParser",
    "UnsupportedFormatError",
    "create_default_registry",
    "decode_bytes",
    "first_non_empty_line",
    "make_document_id",
    "normalize_newlines",
    "parse_file",
    "registry",
]
