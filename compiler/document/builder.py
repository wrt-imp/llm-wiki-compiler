"""Turn parser output into the structured Document Model.

This module is the only place that knows format specific structure:

* Markdown -> one section per heading, nested by heading level
* PDF      -> one section per page (page numbers kept for source tracing)
* TXT      -> one section for the whole file
* anything else -> one section for the whole file

The parsers stay untouched: they hand over normalized text plus parse
metadata, and this module turns that into ``Document.sections``.
"""

from __future__ import annotations

import os
import re
from typing import List, Sequence, Tuple, Union

from .model import (
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    FORMAT_TXT,
    SECTION_KIND_DOCUMENT,
    SECTION_KIND_HEADING,
    SECTION_KIND_PAGE,
    SECTION_KIND_PREAMBLE,
    Document,
    Section,
    make_section_id,
)

PathLike = Union[str, os.PathLike]

#: Same rule the markdown parser uses for headings: ``#`` hashes + a space.
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")


def load_document(path: PathLike) -> Document:
    """Source file -> Parser -> Document Model.

    This is the entry point stage 3 (LLM Extraction) should call.
    """

    # Imported here on purpose: the parser layer already imports this package's
    # model module, and a module level import would make the two hard to read.
    from ..parser import parse_file

    return attach_sections(parse_file(path))


def attach_sections(parsed: Document) -> Document:
    """Return a copy of ``parsed`` with ``sections`` built. Input is untouched."""

    return Document(
        id=parsed.id,
        title=parsed.title,
        source=parsed.source,
        format=parsed.format,
        content=parsed.content,
        sections=build_sections(parsed),
        metadata=dict(parsed.metadata),
    )


def build_sections(parsed: Document) -> List[Section]:
    """Build the top level sections for a parsed document."""

    if parsed.format == FORMAT_MARKDOWN:
        return _markdown_sections(parsed)
    if parsed.format == FORMAT_PDF:
        return _pdf_sections(parsed)
    if parsed.format == FORMAT_TXT:
        return [_whole_document_section(parsed)]
    return [_whole_document_section(parsed)]


# ----------------------------------------------------------------------
# TXT
# ----------------------------------------------------------------------
def _whole_document_section(parsed: Document) -> Section:
    """One section covering the whole document (TXT, or an unknown format)."""

    line_count = max(len(parsed.content.splitlines()), 1)
    return Section(
        id=make_section_id(parsed.id, "1"),
        title=parsed.title,
        content=parsed.content,
        level=1,
        metadata={
            "kind": SECTION_KIND_DOCUMENT,
            "line_start": 1,
            "line_end": line_count,
        },
    )


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------
def _pdf_sections(parsed: Document) -> List[Section]:
    """One section per page, so every page stays traceable."""

    pages = parsed.metadata.get("pages") or []
    if not pages:
        return [_whole_document_section(parsed)]

    sections: List[Section] = []
    for index, page in enumerate(pages, start=1):
        page_number = int(page.get("page_number", index))
        sections.append(
            Section(
                id=make_section_id(parsed.id, str(index)),
                title=f"Page {page_number}",
                content=page.get("text", "") or "",
                level=1,
                metadata={"kind": SECTION_KIND_PAGE, "page_number": page_number},
            )
        )
    return sections


# ----------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------
def _markdown_sections(parsed: Document) -> List[Section]:
    """Build the heading tree, with any text before the first heading kept."""

    lines = parsed.content.splitlines()
    headings = _scan_headings(lines)
    if not headings:
        return [_whole_document_section(parsed)]

    sections: List[Section] = []
    stack: List[Tuple[int, Section]] = []  # (markdown heading level, section)

    preamble_lines = _trim_blank_lines(lines[: headings[0][0]])
    if preamble_lines:
        sections.append(
            Section(
                id="",
                title="",
                content="\n".join(preamble_lines),
                level=1,
                metadata={
                    "kind": SECTION_KIND_PREAMBLE,
                    "line_start": 1,
                    "line_end": headings[0][0],
                },
            )
        )

    for position, (line_index, heading_level, title) in enumerate(headings):
        next_index = (
            headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        )
        while stack and stack[-1][0] >= heading_level:
            stack.pop()
        parent = stack[-1][1] if stack else None

        section = Section(
            id="",
            title=title,
            content="\n".join(_trim_blank_lines(lines[line_index + 1 : next_index])),
            level=parent.level + 1 if parent is not None else 1,
            metadata={
                "kind": SECTION_KIND_HEADING,
                "heading_level": heading_level,
                "line_start": line_index + 1,
                "line_end": max(next_index, line_index + 1),
            },
        )
        if parent is None:
            sections.append(section)
        else:
            parent.children.append(section)
        stack.append((heading_level, section))

    _assign_section_ids(parsed.id, sections)
    return sections


def _scan_headings(lines: Sequence[str]) -> List[Tuple[int, int, str]]:
    """Return ``(line index, heading level, title)`` for real headings.

    Fenced code blocks are skipped, so a ``#`` comment inside a fence is not
    mistaken for a heading.
    """

    headings: List[Tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append(
                (index, len(match.group("hashes")), match.group("text").strip())
            )
    return headings


def _trim_blank_lines(lines: Sequence[str]) -> List[str]:
    """Drop leading/trailing blank lines, keep the content's own indentation."""

    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return list(lines[start:end])


def _assign_section_ids(
    document_id: str, sections: Sequence[Section], prefix: str = ""
) -> None:
    """Number sections by their position, e.g. ``2``, ``2.1``, ``2.1.3``."""

    for index, section in enumerate(sections, start=1):
        path = f"{prefix}.{index}" if prefix else str(index)
        section.id = make_section_id(document_id, path)
        _assign_section_ids(document_id, section.children, path)
