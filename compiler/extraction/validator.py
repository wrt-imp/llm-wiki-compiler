"""Validate the LLM JSON payload and turn it into a Knowledge IR.

Two levels of problems, deliberately:

* contract violations (missing/wrongly typed keys, an item without a name or
  statement) raise :class:`InvalidPayloadError`;
* recoverable issues (an item without sources, a citation that does not exist
  in the document, a duplicate item) are reported as warnings and the rest of
  the payload is still used.

Sources are also made trustworthy: a section id the document does not have is
dropped, and the page number is taken from the cited section rather than from
whatever the model claimed.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..document import Document, Section
from ..knowledge import (
    ENTITY_TYPE_OTHER,
    Concept,
    Entity,
    Fact,
    KnowledgeIR,
    Relation,
    SourceRef,
    normalize_name,
)
from .errors import InvalidPayloadError

#: Top level keys the extraction contract requires.
REQUIRED_KEYS = ("entities", "concepts", "facts", "relations")


def validate_payload(payload: Any, document: Document) -> Tuple[KnowledgeIR, List[str]]:
    """Turn a parsed LLM payload into a :class:`KnowledgeIR`.

    Returns:
        The knowledge found in the payload, plus warnings about what was
        repaired, dropped or ignored.

    Raises:
        InvalidPayloadError: when the payload breaks the JSON contract.
    """

    if not isinstance(payload, dict):
        raise InvalidPayloadError(
            f"payload must be a JSON object, got {type(payload).__name__}"
        )

    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise InvalidPayloadError(
            "payload is missing required field(s): " + ", ".join(missing)
        )
    for key in REQUIRED_KEYS:
        if not isinstance(payload[key], list):
            raise InvalidPayloadError(
                f"'{key}' must be a list, got {type(payload[key]).__name__}"
            )

    warnings: List[str] = []
    unknown = [key for key in payload if key not in REQUIRED_KEYS]
    if unknown:
        warnings.append(
            "ignored unknown top-level field(s): " + ", ".join(sorted(unknown))
        )

    context = _DocumentContext(document)

    entities = [
        _build_entity(item, index, context, warnings)
        for index, item in _items(payload["entities"], "entities")
    ]
    concepts = [
        _build_concept(item, index, context, warnings)
        for index, item in _items(payload["concepts"], "concepts")
    ]
    facts = [
        _build_fact(item, index, context, warnings)
        for index, item in _items(payload["facts"], "facts")
    ]
    relations = [
        _build_relation(item, index, context, warnings)
        for index, item in _items(payload["relations"], "relations")
    ]

    _resolve_relation_endpoints(relations, context, warnings)

    entities = _merge_duplicates(
        entities, "entities", warnings, _merge_named_item
    )
    concepts = _merge_duplicates(
        concepts, "concepts", warnings, _merge_named_item
    )
    facts = _merge_duplicates(facts, "facts", warnings, None)
    relations = _merge_duplicates(relations, "relations", warnings, None)

    knowledge = KnowledgeIR(
        document_id=document.id,
        document_title=document.title,
        source=document.source,
        entities=entities,
        concepts=concepts,
        facts=facts,
        relations=relations,
    )
    return knowledge, warnings


# ----------------------------------------------------------------------
# Items
# ----------------------------------------------------------------------
def _items(value: Sequence[Any], key: str):
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise InvalidPayloadError(
                f"{key}[{index}] must be an object, got {type(item).__name__}"
            )
        yield index, item


def _build_entity(
    item: Dict[str, Any], index: int, context: "_DocumentContext", warnings: List[str]
) -> Entity:
    where = f"entities[{index}]"
    entity = Entity(
        name=_require_text(item, "name", where),
        type=_optional_text(item, "type", where) or ENTITY_TYPE_OTHER,
        description=_optional_text(item, "description", where),
        aliases=_string_list(item, "aliases", where, warnings),
        sources=_build_sources(item, where, context, warnings),
    )
    context.register(entity.id, entity.name)
    return entity


def _build_concept(
    item: Dict[str, Any], index: int, context: "_DocumentContext", warnings: List[str]
) -> Concept:
    where = f"concepts[{index}]"
    concept = Concept(
        name=_require_text(item, "name", where),
        description=_optional_text(item, "description", where),
        aliases=_string_list(item, "aliases", where, warnings),
        sources=_build_sources(item, where, context, warnings),
    )
    context.register(concept.id, concept.name)
    return concept


def _build_fact(
    item: Dict[str, Any], index: int, context: "_DocumentContext", warnings: List[str]
) -> Fact:
    where = f"facts[{index}]"
    return Fact(
        statement=_require_text(item, "statement", where),
        subject=_optional_text(item, "subject", where),
        predicate=_optional_text(item, "predicate", where),
        object=_optional_text(item, "object", where),
        sources=_build_sources(item, where, context, warnings),
    )


def _build_relation(
    item: Dict[str, Any], index: int, context: "_DocumentContext", warnings: List[str]
) -> Relation:
    where = f"relations[{index}]"
    return Relation(
        source=_require_text(item, "source", where),
        target=_require_text(item, "target", where),
        type=_optional_text(item, "type", where),
        description=_optional_text(item, "description", where),
        sources=_build_sources(item, where, context, warnings),
    )


def _resolve_relation_endpoints(
    relations: Sequence[Relation], context: "_DocumentContext", warnings: List[str]
) -> None:
    unresolved: List[str] = []
    for relation in relations:
        relation.source_id = context.resolve(relation.source)
        relation.target_id = context.resolve(relation.target)
        for endpoint in (relation.source, relation.target):
            if context.resolve(endpoint) is None and endpoint not in unresolved:
                unresolved.append(endpoint)
    for name in unresolved:
        warnings.append(
            f"relation endpoint '{name}' does not match any extracted entity or concept"
        )


def _merge_duplicates(
    items: Sequence[Any],
    key: str,
    warnings: List[str],
    merge_extras: Optional[Callable[[Any, Any], None]],
) -> List[Any]:
    merged: Dict[str, Any] = {}
    for item in items:
        existing = merged.get(item.id)
        if existing is None:
            merged[item.id] = item
            continue
        warnings.append(f"duplicate {key} '{_label(item)}' merged")
        existing.sources = _union_sources(existing.sources, item.sources)
        if not existing.description and item.description:
            existing.description = item.description
        if merge_extras is not None:
            merge_extras(existing, item)
    return list(merged.values())


def _merge_named_item(existing: Any, item: Any) -> None:
    for alias in item.aliases:
        if alias not in existing.aliases:
            existing.aliases.append(alias)


def _label(item: Any) -> str:
    if isinstance(item, Fact):
        return item.statement
    if isinstance(item, Relation):
        return f"{item.source} -> {item.target}"
    return item.name


def _union_sources(first: Sequence[SourceRef], second: Sequence[SourceRef]) -> List[SourceRef]:
    result = list(first)
    seen = {_source_key(source) for source in first}
    for source in second:
        if _source_key(source) not in seen:
            seen.add(_source_key(source))
            result.append(source)
    return result


def _source_key(source: SourceRef) -> Tuple[Optional[str], Optional[int], str]:
    return (source.section_id, source.page_number, source.quote)


# ----------------------------------------------------------------------
# Field helpers
# ----------------------------------------------------------------------
def _require_text(item: Dict[str, Any], key: str, where: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidPayloadError(f"{where}: '{key}' must be a non-empty string")
    return value.strip()


def _optional_text(item: Dict[str, Any], key: str, where: str) -> str:
    value = item.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidPayloadError(f"{where}: '{key}' must be a string when present")
    return value.strip()


def _string_list(
    item: Dict[str, Any], key: str, where: str, warnings: List[str]
) -> List[str]:
    value = item.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidPayloadError(f"{where}: '{key}' must be a list when present")
    result: List[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            if entry.strip() not in result:
                result.append(entry.strip())
        else:
            warnings.append(f"{where}: ignored '{key}' entry that is not a string")
    return result


def _build_sources(
    item: Dict[str, Any], where: str, context: "_DocumentContext", warnings: List[str]
) -> List[SourceRef]:
    value = item.get("sources")
    if value is None:
        warnings.append(f"{where}: no sources given")
        return []
    if not isinstance(value, list):
        raise InvalidPayloadError(f"{where}: 'sources' must be a list when present")

    sources: List[SourceRef] = []
    for index, entry in enumerate(value):
        source = _build_source(entry, f"{where}.sources[{index}]", context, warnings)
        if source is not None:
            sources.append(source)
    if not sources:
        warnings.append(f"{where}: 'sources' is empty")
    return sources


def _build_source(
    entry: Any, where: str, context: "_DocumentContext", warnings: List[str]
) -> Optional[SourceRef]:
    if not isinstance(entry, dict):
        warnings.append(f"{where}: ignored source entry that is not an object")
        return None

    section_id = entry.get("section_id")
    if section_id is not None and not isinstance(section_id, str):
        warnings.append(f"{where}: ignored non-string section_id")
        section_id = None
    if isinstance(section_id, str):
        section_id = section_id.strip() or None
    if section_id is not None and not context.has_section(section_id):
        warnings.append(f"{where}: unknown section id '{section_id}' dropped")
        section_id = None

    page_number = _optional_int(entry.get("page_number"), where, "page_number", warnings)
    section_page = context.page_of(section_id)
    if section_page is not None:
        if page_number is not None and page_number != section_page:
            warnings.append(
                f"{where}: page {page_number} does not match section {section_id} "
                f"(page {section_page}); the section page is used"
            )
        page_number = section_page
    elif page_number is not None and context.has_pages() and not context.has_page(
        page_number
    ):
        warnings.append(f"{where}: unknown page number {page_number} dropped")
        page_number = None

    quote = entry.get("quote")
    if quote is None:
        quote = ""
    if not isinstance(quote, str):
        warnings.append(f"{where}: ignored non-string quote")
        quote = ""

    return SourceRef(
        document_id=context.document_id,
        section_id=section_id,
        page_number=page_number,
        quote=quote.strip(),
    )


def _optional_int(
    value: Any, where: str, key: str, warnings: List[str]
) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        warnings.append(f"{where}: ignored boolean {key}")
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    warnings.append(f"{where}: ignored invalid {key} {value!r}")
    return None


class _DocumentContext:
    """What the document actually contains, for checking citations."""

    def __init__(self, document: Document) -> None:
        self.document_id = document.id
        self._sections: Dict[str, Section] = {
            section.id: section for section in document.walk_sections()
        }
        self._pages = set()
        for section in self._sections.values():
            page = section.metadata.get("page_number")
            if isinstance(page, int):
                self._pages.add(page)
        for page_entry in document.metadata.get("pages") or []:
            if isinstance(page_entry, dict) and isinstance(
                page_entry.get("page_number"), int
            ):
                self._pages.add(page_entry["page_number"])
        self._names: Dict[str, str] = {}

    def has_section(self, section_id: str) -> bool:
        return section_id in self._sections

    def page_of(self, section_id: Optional[str]) -> Optional[int]:
        if section_id is None:
            return None
        section = self._sections.get(section_id)
        if section is None:
            return None
        page = section.metadata.get("page_number")
        return page if isinstance(page, int) else None

    def has_pages(self) -> bool:
        return bool(self._pages)

    def has_page(self, page_number: int) -> bool:
        return page_number in self._pages

    def register(self, knowledge_id: str, name: str) -> None:
        normalized = normalize_name(name)
        if normalized and normalized not in self._names:
            self._names[normalized] = knowledge_id

    def resolve(self, name: str) -> Optional[str]:
        return self._names.get(normalize_name(name))
