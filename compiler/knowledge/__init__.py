"""Stage 3 of the LLM Wiki Compiler: the Knowledge IR.

The IR is the validated result of extracting knowledge from *one* document::

    >>> from compiler.knowledge import Entity, KnowledgeIR
    >>> knowledge = KnowledgeIR(document_id="abc", entities=[Entity(name="parser")])
    >>> knowledge.counts()["entities"]
    1

Cross-document merging, wiki generation, linking, search and graph work are not
implemented yet.
"""

from .model import (
    ENTITY_TYPES,
    ENTITY_TYPE_ORGANIZATION,
    ENTITY_TYPE_OTHER,
    ENTITY_TYPE_PERSON,
    ENTITY_TYPE_SYSTEM,
    KIND_CONCEPT,
    KIND_ENTITY,
    KIND_FACT,
    KIND_RELATION,
    Concept,
    Entity,
    Fact,
    KnowledgeIR,
    Relation,
    SourceRef,
    make_knowledge_id,
    normalize_name,
)

__all__ = [
    "Concept",
    "ENTITY_TYPES",
    "ENTITY_TYPE_ORGANIZATION",
    "ENTITY_TYPE_OTHER",
    "ENTITY_TYPE_PERSON",
    "ENTITY_TYPE_SYSTEM",
    "Entity",
    "Fact",
    "KIND_CONCEPT",
    "KIND_ENTITY",
    "KIND_FACT",
    "KIND_RELATION",
    "KnowledgeIR",
    "Relation",
    "SourceRef",
    "make_knowledge_id",
    "normalize_name",
]
