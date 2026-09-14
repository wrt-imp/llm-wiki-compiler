"""Backwards compatible imports for the document structure.

``Document`` (and the format constants and id helper) live in
:mod:`compiler.document.model` since the Document Model stage was added. There
is exactly one ``Document`` class: the parsers still import it from here, and
so can any code written against the parser stage.
"""

from ..document.model import (  # noqa: F401  (re-exported on purpose)
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    FORMAT_TXT,
    SUPPORTED_FORMATS,
    Document,
    make_document_id,
)

__all__ = [
    "Document",
    "FORMAT_MARKDOWN",
    "FORMAT_PDF",
    "FORMAT_TXT",
    "SUPPORTED_FORMATS",
    "make_document_id",
]
