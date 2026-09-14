"""PDF parser built on pypdf."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from pypdf import PdfReader

from .base import BaseParser, PathLike, first_non_empty_line
from .document import FORMAT_PDF, Document
from .encoding import normalize_newlines
from .errors import ParserError


class PdfParser(BaseParser):
    """PDF -> Document, keeping per page text for later source tracing.

    ``metadata["pages"]`` holds ``{"page_number": int, "text": str}`` entries
    for every page, so a later stage can point at the page a statement came
    from. ``content`` is the same text joined in reading order, and
    ``metadata["pdf_metadata"]`` carries the document information dictionary.
    """

    format = FORMAT_PDF
    extensions = (".pdf",)

    def parse(self, path: PathLike) -> Document:
        source = self._resolve_source(path)
        reader = self._open_reader(source)

        pages: List[Dict[str, Any]] = []
        empty_pages: List[int] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = self._extract_page_text(source, page_number, page)
            if not text:
                empty_pages.append(page_number)
            pages.append({"page_number": page_number, "text": text})

        content = "\n\n".join(page["text"] for page in pages)
        pdf_metadata = _document_information(reader)

        title = pdf_metadata.get("title", "").strip()
        if not title:
            first_page = pages[0]["text"] if pages else ""
            title = first_non_empty_line(first_page)

        metadata: Dict[str, Any] = {
            "page_count": len(pages),
            "pages": pages,
            "pdf_metadata": pdf_metadata,
            "encrypted": bool(reader.is_encrypted),
            "empty_pages": empty_pages,
        }
        return self._build_document(
            source, title=title, content=content, metadata=metadata
        )

    def _open_reader(self, source) -> PdfReader:
        try:
            reader = PdfReader(str(source))
        except Exception as exc:  # pypdf raises several unrelated error types
            raise ParserError(f"cannot read PDF file '{source}': {exc}") from exc

        if reader.is_encrypted:
            try:
                reader.decrypt("")  # many PDFs are "encrypted" with no password
            except Exception:
                pass
            if reader.is_encrypted:
                raise ParserError(
                    f"PDF file '{source}' is encrypted and needs a password"
                )
        return reader

    def _extract_page_text(self, source, page_number: int, page) -> str:
        try:
            raw = page.extract_text() or ""
        except Exception as exc:
            raise ParserError(
                f"cannot extract text from page {page_number} of '{source}': {exc}"
            ) from exc
        return normalize_newlines(raw).strip()


def _document_information(reader: PdfReader) -> Dict[str, str]:
    """Return the PDF document information dictionary as plain strings."""

    information: Dict[str, str] = {}
    raw_metadata = reader.metadata
    if not raw_metadata:
        return information

    try:
        items = raw_metadata.items()
    except AttributeError:  # pragma: no cover - defensive
        return information

    for key, value in items:
        name = str(key).lstrip("/").lower()
        information[name] = _stringify(value)
    return information


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value).strip()
