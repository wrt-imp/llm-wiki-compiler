"""Prompt construction for knowledge extraction.

The document is handed to the model as labelled section blocks, so citations in
the answer can point at real ``Section.id``s and page numbers.
"""

from __future__ import annotations

from typing import List

from ..document import Document, Section

#: Bumped whenever the prompt wording changes; stored on every result.
PROMPT_VERSION = "extraction-v1"

SYSTEM_PROMPT = """\
You extract structured knowledge from ONE source document for a knowledge wiki.

Rules:
1. Extract only knowledge that the document text directly supports.
2. Never add outside knowledge, never infer missing facts, never complete gaps.
3. Separate the four kinds of knowledge and keep them distinct:
   - entity: a concrete named thing (person, organization, system, product, document, place, event)
   - concept: an abstract idea, topic or technique (for example "knowledge graph", "encoding detection")
   - fact: one statement the document makes, with subject/predicate/object when the text allows
   - relation: a directed link between two entities or concepts, with a short type such as "uses" or "part of"
4. Keep provenance. For every item fill "sources" with the sections it came from: use the exact
   section id shown in the input, and copy a short verbatim quote (at most 200 characters) from that
   section. Never invent a section id or a quote.
5. Answer with ONE JSON object and nothing else. No markdown, no code fences, no comments, no
   explanation, no text before or after the JSON.
6. If the document contains no extractable knowledge, return the four arrays empty.
7. Write names, statements and descriptions in the language of the document. Do not translate.
8. Do not summarise the document and do not produce wiki text: only the JSON object below.

JSON shape (all four keys are always present, each an array):
{
  "entities": [
    {"name": "string", "type": "string", "description": "string", "aliases": ["string"],
     "sources": [{"section_id": "string", "page_number": 1, "quote": "string"}]}
  ],
  "concepts": [
    {"name": "string", "description": "string", "aliases": ["string"],
     "sources": [{"section_id": "string", "page_number": 1, "quote": "string"}]}
  ],
  "facts": [
    {"statement": "string", "subject": "string", "predicate": "string", "object": "string",
     "sources": [{"section_id": "string", "page_number": 1, "quote": "string"}]}
  ],
  "relations": [
    {"source": "string", "target": "string", "type": "string", "description": "string",
     "sources": [{"section_id": "string", "page_number": 1, "quote": "string"}]}
  ]
}

Use "page_number": null when the source has no page. When a document has no section ids, use
"section_id": null.
"""


def build_extraction_prompt(document: Document) -> tuple[str, str]:
    """Return the ``(system_prompt, user_prompt)`` pair for a document."""

    return SYSTEM_PROMPT, build_user_prompt(document)


def build_user_prompt(document: Document) -> str:
    """Render the document as section blocks the model can cite."""

    lines: List[str] = [
        "Document",
        f"id: {document.id}",
        f"title: {document.title}",
        f"source: {document.source}",
        f"format: {document.format}",
        "",
    ]

    sections = list(document.walk_sections()) if document.sections else []
    if sections:
        lines.append(
            'Sections (cite these ids in "sources"; a section header is not part of its text):'
        )
        for section in sections:
            lines.append("")
            lines.append(_section_header(section))
            if section.title:
                lines.append(section.title)
            lines.append(section.content)
    else:
        lines.append(
            'This document has no section ids: return "section_id": null in every source, and the '
            "full text is below."
        )
        lines.append("")
        lines.append(document.content)

    lines.append("")
    lines.append("Now return the JSON object.")
    return "\n".join(lines)


def _section_header(section: Section) -> str:
    page = section.metadata.get("page_number")
    if isinstance(page, int):
        return f"[section {section.id} | page {page}]"
    return f"[section {section.id}]"
