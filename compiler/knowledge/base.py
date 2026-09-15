"""The unified knowledge base: the output of the Semantic Merge stage.

Stage 4 of the LLM Wiki Compiler::

    Knowledge IR A + Knowledge IR B + ... -> Semantic Merge -> KnowledgeBase

The knowledge base keeps the same item types as the per-document Knowledge IR
(entity, concept, fact, relation) plus the list of documents that contributed
to it. Every item still carries its :class:`~compiler.knowledge.model.SourceRef`
entries, so merging never loses provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .model import Concept, Entity, Fact, Relation


@dataclass
class KnowledgeBase:
    """Merged knowledge from one or more documents.

    Attributes:
        entities: Deduplicated entities, one entry per knowledge object.
        concepts: Deduplicated concepts.
        facts: Deduplicated facts.
        relations: Deduplicated relations between entities/concepts.
        documents: ``{"id", "title", "source"}`` for every contributing document.
        metadata: Merge bookkeeping: groups, judge statistics, warnings, counts.
    """

    entities: List[Entity] = field(default_factory=list)
    concepts: List[Concept] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    documents: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        """Item counts, handy for logs and tests."""

        return {
            "entities": len(self.entities),
            "concepts": len(self.concepts),
            "facts": len(self.facts),
            "relations": len(self.relations),
        }

    def is_empty(self) -> bool:
        """Return ``True`` when the knowledge base holds no knowledge."""

        return not (self.entities or self.concepts or self.facts or self.relations)

    def document_ids(self) -> List[str]:
        """Ids of the documents that contributed, in insertion order."""

        return [str(doc["id"]) for doc in self.documents if doc.get("id")]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [entity.to_dict() for entity in self.entities],
            "concepts": [concept.to_dict() for concept in self.concepts],
            "facts": [fact.to_dict() for fact in self.facts],
            "relations": [relation.to_dict() for relation in self.relations],
            "documents": [dict(document) for document in self.documents],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeBase":
        return cls(
            entities=[Entity.from_dict(item) for item in data.get("entities", [])],
            concepts=[Concept.from_dict(item) for item in data.get("concepts", [])],
            facts=[Fact.from_dict(item) for item in data.get("facts", [])],
            relations=[
                Relation.from_dict(item) for item in data.get("relations", [])
            ],
            documents=[dict(document) for document in data.get("documents", [])],
            metadata=dict(data.get("metadata", {})),
        )
