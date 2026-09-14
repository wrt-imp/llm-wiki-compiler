"""The Knowledge IR: the knowledge extracted from one document.

This is stage 3 of the LLM Wiki Compiler::

    Source Files -> Parser -> Document Model -> LLM Extraction -> Knowledge IR

Keep the two models apart:

* the Document Model describes *what the source is and how it is organized*
  (text, sections, pages, encoding);
* the Knowledge IR describes *what knowledge the source contains* (entities,
  concepts, facts, relations).

Relations between knowledge and the text are kept as :class:`SourceRef`, so
every extracted item can be traced back to a document, a section, a page and a
verbatim quote. The IR contains no wiki links, no markdown, no summaries and no
vectors - generating wiki pages is a later stage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Item kinds, used when deriving stable ids.
KIND_ENTITY = "entity"
KIND_CONCEPT = "concept"
KIND_FACT = "fact"
KIND_RELATION = "relation"

#: Suggested entity types. The field stays a free string: models often need a
#: more precise label than "other", and validation only requires it to be text.
ENTITY_TYPE_PERSON = "person"
ENTITY_TYPE_ORGANIZATION = "organization"
ENTITY_TYPE_SYSTEM = "system"
ENTITY_TYPE_DOCUMENT = "document"
ENTITY_TYPE_PRODUCT = "product"
ENTITY_TYPE_PLACE = "place"
ENTITY_TYPE_EVENT = "event"
ENTITY_TYPE_OTHER = "other"

ENTITY_TYPES = (
    ENTITY_TYPE_PERSON,
    ENTITY_TYPE_ORGANIZATION,
    ENTITY_TYPE_SYSTEM,
    ENTITY_TYPE_DOCUMENT,
    ENTITY_TYPE_PRODUCT,
    ENTITY_TYPE_PLACE,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_OTHER,
)


def normalize_name(name: str) -> str:
    """Normalize a name for comparisons and id derivation."""

    return " ".join(str(name).split()).strip().casefold()


def make_knowledge_id(kind: str, key: str) -> str:
    """Return a stable id for a piece of knowledge.

    The id depends on the normalized key only - not on the document it was
    found in - so the same entity mentioned in two documents gets the same id,
    which is what a later merge stage needs.
    """

    digest = hashlib.sha1(f"{kind}:{normalize_name(key)}".encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass
class SourceRef:
    """Where a piece of knowledge comes from.

    Attributes:
        document_id: ``Document.id`` of the source document.
        section_id: ``Section.id`` inside that document, when known.
        page_number: PDF page number, when known.
        quote: Short verbatim excerpt from the source text.
    """

    document_id: str
    section_id: Optional[str] = None
    page_number: Optional[int] = None
    quote: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "section_id": self.section_id,
            "page_number": self.page_number,
            "quote": self.quote,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceRef":
        return cls(
            document_id=data["document_id"],
            section_id=data.get("section_id"),
            page_number=data.get("page_number"),
            quote=data.get("quote", ""),
        )


@dataclass
class Entity:
    """A concrete named thing: person, organization, system, product, ..."""

    name: str
    type: str = ENTITY_TYPE_OTHER
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    sources: List[SourceRef] = field(default_factory=list)
    #: Derived from the name; pass it explicitly only when restoring a saved IR.
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_knowledge_id(KIND_ENTITY, self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "aliases": list(self.aliases),
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        return cls(
            name=data["name"],
            type=data.get("type", ENTITY_TYPE_OTHER),
            description=data.get("description", ""),
            aliases=[str(alias) for alias in data.get("aliases", [])],
            sources=[SourceRef.from_dict(s) for s in data.get("sources", [])],
            id=data.get("id", ""),
        )


@dataclass
class Concept:
    """An abstract idea, topic or technique."""

    name: str
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    sources: List[SourceRef] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_knowledge_id(KIND_CONCEPT, self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "aliases": list(self.aliases),
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Concept":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            aliases=[str(alias) for alias in data.get("aliases", [])],
            sources=[SourceRef.from_dict(s) for s in data.get("sources", [])],
            id=data.get("id", ""),
        )


@dataclass
class Fact:
    """One statement the document makes, ideally as subject/predicate/object."""

    statement: str
    subject: str = ""
    predicate: str = ""
    object: str = ""
    sources: List[SourceRef] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_knowledge_id(KIND_FACT, self.statement)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Fact":
        return cls(
            statement=data["statement"],
            subject=data.get("subject", ""),
            predicate=data.get("predicate", ""),
            object=data.get("object", ""),
            sources=[SourceRef.from_dict(s) for s in data.get("sources", [])],
            id=data.get("id", ""),
        )


@dataclass
class Relation:
    """A directed link between two entities or concepts.

    ``source`` and ``target`` are the names as written in the document.
    ``source_id`` / ``target_id`` are filled in when the name matches a known
    entity or concept; unresolved endpoints are kept as names only.
    """

    source: str
    target: str
    type: str = ""
    description: str = ""
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    sources: List[SourceRef] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_knowledge_id(
                KIND_RELATION, f"{self.source}|{self.type}|{self.target}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "description": self.description,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relation":
        return cls(
            source=data["source"],
            target=data["target"],
            type=data.get("type", ""),
            description=data.get("description", ""),
            source_id=data.get("source_id"),
            target_id=data.get("target_id"),
            sources=[SourceRef.from_dict(s) for s in data.get("sources", [])],
            id=data.get("id", ""),
        )


@dataclass
class KnowledgeIR:
    """Everything one document contributed to the knowledge base."""

    document_id: str
    document_title: str = ""
    source: str = ""
    entities: List[Entity] = field(default_factory=list)
    concepts: List[Concept] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Return ``True`` when the document yielded no knowledge at all."""

        return not (self.entities or self.concepts or self.facts or self.relations)

    def counts(self) -> Dict[str, int]:
        """Item counts, handy for logs and tests."""

        return {
            "entities": len(self.entities),
            "concepts": len(self.concepts),
            "facts": len(self.facts),
            "relations": len(self.relations),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "source": self.source,
            "entities": [entity.to_dict() for entity in self.entities],
            "concepts": [concept.to_dict() for concept in self.concepts],
            "facts": [fact.to_dict() for fact in self.facts],
            "relations": [relation.to_dict() for relation in self.relations],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeIR":
        return cls(
            document_id=data["document_id"],
            document_title=data.get("document_title", ""),
            source=data.get("source", ""),
            entities=[Entity.from_dict(item) for item in data.get("entities", [])],
            concepts=[Concept.from_dict(item) for item in data.get("concepts", [])],
            facts=[Fact.from_dict(item) for item in data.get("facts", [])],
            relations=[
                Relation.from_dict(item) for item in data.get("relations", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )
