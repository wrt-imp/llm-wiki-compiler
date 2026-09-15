"""Render a KnowledgeBase as Markdown.

No links are produced here - not ``[[wiki links]]`` and not markdown links.
Internal linking is the Link Resolver's job; this stage only writes readable
pages and never invents references that are not backed by the knowledge base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from ..knowledge import Fact, KnowledgeBase, Relation, SourceRef
from ..merge.normalize import alias_keys, match_key, statement_key
from .paths import DEFAULT_EXTENSION, PageTarget, WikiPage

#: Bumped whenever the rendered layout changes; stored on every build.
GENERATOR_VERSION = "wiki-generator-v1"

KIND_ENTITY = "entity"
KIND_CONCEPT = "concept"
KIND_INDEX = "index"

_KIND_ORDER = {KIND_ENTITY: 0, KIND_CONCEPT: 1}

#: How much of a source quote is repeated on the page.
MAX_QUOTE_CHARS = 300


@dataclass(frozen=True)
class RelationSlot:
    """A relation shown on a page, with the role this page plays."""

    relation: Relation
    #: ``"out"`` when the page is the source, ``"in"`` when it is the target.
    direction: str

    @property
    def sort_key(self) -> Tuple[str, str, str, str]:
        relation = self.relation
        return (
            match_key(relation.source),
            match_key(relation.type),
            match_key(relation.target),
            relation.id,
        )


@dataclass
class PagePlan:
    """Everything that goes onto one page."""

    target: PageTarget
    description: str
    item_type: str = ""
    own_sources: List[SourceRef] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    relations: List[RelationSlot] = field(default_factory=list)

    def all_sources(self) -> List[SourceRef]:
        """Own sources plus the evidence of everything shown on the page."""

        groups: List[Iterable[SourceRef]] = [self.own_sources]
        groups.extend(fact.sources for fact in self.facts)
        groups.extend(slot.relation.sources for slot in self.relations)
        return ordered_sources(groups)


@dataclass
class WikiPlan:
    """The whole wiki before any file is written."""

    pages: List[PagePlan] = field(default_factory=list)
    documents: List[Dict[str, Any]] = field(default_factory=list)
    unattached_facts: List[Fact] = field(default_factory=list)
    unattached_relations: List[Relation] = field(default_factory=list)


def build_plan(knowledge_base: KnowledgeBase) -> WikiPlan:
    """Decide the pages and which fact/relation belongs to which page."""

    targets: List[PageTarget] = []
    plans: List[PagePlan] = []
    for entity in knowledge_base.entities:
        targets.append(_target(KIND_ENTITY, entity))
        plans.append(
            PagePlan(
                target=targets[-1],
                description=entity.description,
                item_type=entity.type,
                own_sources=list(entity.sources),
            )
        )
    for concept in knowledge_base.concepts:
        targets.append(_target(KIND_CONCEPT, concept))
        plans.append(
            PagePlan(
                target=targets[-1],
                description=concept.description,
                own_sources=list(concept.sources),
            )
        )

    order = sorted(
        range(len(targets)),
        key=lambda index: (
            _KIND_ORDER.get(targets[index].kind, 99),
            match_key(targets[index].title),
            targets[index].object_id,
        ),
    )
    targets = [targets[index] for index in order]
    plans = [plans[index] for index in order]

    keys_per_page: List[Set[str]] = [
        set(alias_keys(target.title, target.aliases)) for target in targets
    ]
    by_key: Dict[str, List[int]] = {}
    for index, keys in enumerate(keys_per_page):
        for key in keys:
            by_key.setdefault(key, []).append(index)

    unattached_facts: List[Fact] = []
    for fact in sorted(knowledge_base.facts, key=_fact_sort_key):
        pages = _matching_pages(by_key, fact.subject, fact.object)
        if not pages:
            unattached_facts.append(fact)
        for index in pages:
            plans[index].facts.append(fact)

    unattached_relations: List[Relation] = []
    for relation in sorted(knowledge_base.relations, key=_relation_sort_key):
        pages = _matching_pages(by_key, relation.source, relation.target)
        if not pages:
            unattached_relations.append(relation)
            continue
        for index in pages:
            plans[index].relations.append(
                RelationSlot(
                    relation=relation,
                    direction="out"
                    if match_key(relation.source) in keys_per_page[index]
                    else "in",
                )
            )

    return WikiPlan(
        pages=plans,
        documents=[dict(document) for document in knowledge_base.documents],
        unattached_facts=unattached_facts,
        unattached_relations=unattached_relations,
    )


def render_page(
    page: WikiPage, plan: PagePlan, *, front_matter: bool = True
) -> str:
    """Render one knowledge object page."""

    sources = plan.all_sources()
    numbers = {_source_key(source): index + 1 for index, source in enumerate(sources)}

    lines: List[str] = []
    if front_matter:
        lines.extend(_front_matter(page, plan))
    lines.append(f"# {page.title}")
    lines.append("")

    if plan.description:
        lines.extend(["## Description", "", plan.description, ""])

    if plan.facts:
        lines.append("## Facts")
        lines.append("")
        for fact in plan.facts:
            lines.append(f"- {fact.statement}{_markers(fact.sources, numbers)}")
        lines.append("")

    if plan.relations:
        lines.append("## Relations")
        lines.append("")
        for slot in plan.relations:
            line = f"- {relation_text(slot)}"
            line += _markers(slot.relation.sources, numbers)
            lines.append(line)
        lines.append("")

    if sources:
        lines.append("## Sources")
        lines.append("")
        for number, source in enumerate(sources, start=1):
            lines.append(source_line(number, source))
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_index(
    plan: WikiPlan,
    pages: Sequence[WikiPage],
    *,
    extension: str = DEFAULT_EXTENSION,
) -> str:
    """Render the overview page (also home of unattached knowledge)."""

    by_object = {(page.kind, page.object_id): page.path for page in pages}
    entity_pages = [page for page in pages if page.kind == KIND_ENTITY]
    concept_pages = [page for page in pages if page.kind == KIND_CONCEPT]

    lines: List[str] = ["# Knowledge Wiki", ""]
    lines.append(
        " · ".join(
            [
                f"{len(plan.documents)} document(s)",
                f"{len(entity_pages)} entity page(s)",
                f"{len(concept_pages)} concept page(s)",
                f"{len(plan.unattached_facts)} unattached fact(s)",
                f"{len(plan.unattached_relations)} unattached relation(s)",
            ]
        )
    )
    lines.append("")

    if plan.documents:
        lines.extend(["## Documents", ""])
        for document in sorted(plan.documents, key=lambda item: str(item.get("id", ""))):
            title = str(document.get("title", "") or document.get("id", ""))
            source = str(document.get("source", ""))
            suffix = f" ({source})" if source else ""
            lines.append(f"- `{document.get('id', '')}` — {title}{suffix}")
        lines.append("")

    for heading, kind_pages in (("Entities", entity_pages), ("Concepts", concept_pages)):
        lines.extend([f"## {heading}", ""])
        if kind_pages:
            for page in kind_pages:
                lines.append(f"- {page.title} → {page.path}")
        else:
            lines.append("- (none)")
        lines.append("")

    unattached_sources: List[Iterable[SourceRef]] = []
    unattached_sources.extend(fact.sources for fact in plan.unattached_facts)
    unattached_sources.extend(
        relation.sources for relation in plan.unattached_relations
    )
    sources = ordered_sources(unattached_sources)
    numbers = {_source_key(source): index + 1 for index, source in enumerate(sources)}

    lines.extend(["## Unattached Facts", ""])
    if plan.unattached_facts:
        for fact in plan.unattached_facts:
            lines.append(f"- {fact.statement}{_markers(fact.sources, numbers)}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.extend(["## Unattached Relations", ""])
    if plan.unattached_relations:
        for relation in plan.unattached_relations:
            slot = RelationSlot(relation=relation, direction="out")
            lines.append(f"- {relation_text(slot)}{_markers(relation.sources, numbers)}")
    else:
        lines.append("- (none)")
    lines.append("")

    if sources:
        lines.extend(["## Sources", ""])
        for number, source in enumerate(sources, start=1):
            lines.append(source_line(number, source))
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def relation_text(slot: RelationSlot) -> str:
    """``A —type→ B``, prefixed with ``←`` on the target's page."""

    relation = slot.relation
    arrow = f"—{relation.type}→" if relation.type else "→"
    text = f"{relation.source} {arrow} {relation.target}"
    return f"← {text}" if slot.direction == "in" else text


def source_line(number: int, source: SourceRef) -> str:
    """One numbered entry of a ``## Sources`` list."""

    parts = [f"**{source.document_id}**"]
    if source.section_id:
        parts.append(f"section `{source.section_id}`")
    if source.page_number is not None:
        parts.append(f"page {source.page_number}")
    line = f"{number}. " + " · ".join(parts)
    quote = " ".join(str(source.quote or "").split())
    if quote:
        if len(quote) > MAX_QUOTE_CHARS:
            quote = quote[:MAX_QUOTE_CHARS].rstrip() + "…"
        line += f" — “{quote}”"
    return line


def ordered_sources(groups: Iterable[Iterable[SourceRef]]) -> List[SourceRef]:
    """De-duplicated sources in a stable order (this drives the numbering)."""

    seen = set()
    unique: List[SourceRef] = []
    for group in groups:
        for source in group:
            key = _source_key(source)
            if key not in seen:
                seen.add(key)
                unique.append(source)
    return sorted(unique, key=_source_sort_key)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _target(kind: str, item: Any) -> PageTarget:
    return PageTarget(
        kind=kind,
        object_id=item.id,
        title=item.name,
        aliases=tuple(item.aliases),
    )


def _matching_pages(
    by_key: Dict[str, List[int]], *names: str
) -> List[int]:
    found: List[int] = []
    for name in names:
        if not name:
            continue
        for index in by_key.get(match_key(name), []):
            if index not in found:
                found.append(index)
    return sorted(found)


def _fact_sort_key(fact: Fact) -> Tuple[str, str]:
    return (statement_key(fact.statement), fact.id)


def _relation_sort_key(relation: Relation) -> Tuple[str, str, str, str]:
    return (
        match_key(relation.source),
        match_key(relation.type),
        match_key(relation.target),
        relation.id,
    )


def _source_sort_key(source: SourceRef) -> Tuple[str, str, int, str]:
    return (
        str(source.document_id),
        str(source.section_id or ""),
        source.page_number if source.page_number is not None else -1,
        str(source.quote or ""),
    )


def _source_key(source: SourceRef) -> Tuple[str, Any, Any, str]:
    return (
        str(source.document_id),
        source.section_id,
        source.page_number,
        str(source.quote or ""),
    )


def _markers(sources: Iterable[SourceRef], numbers: Dict[Any, int]) -> str:
    marks = [
        numbers[key]
        for key in (_source_key(source) for source in sources)
        if key in numbers
    ]
    if not marks:
        return ""
    return " " + "".join(f"[{number}]" for number in sorted(set(marks)))


def _front_matter(page: WikiPage, plan: PagePlan) -> List[str]:
    lines = ["---", f"id: {_yaml_scalar(page.object_id)}", f"kind: {_yaml_scalar(page.kind)}"]
    if plan.item_type:
        lines.append(f"type: {_yaml_scalar(plan.item_type)}")
    if page.aliases:
        lines.append("aliases:")
        for alias in page.aliases:
            lines.append(f"  - {_yaml_scalar(alias)}")
    lines.append(f"page: {_yaml_scalar(page.path)}")
    lines.append("---")
    return lines


def _yaml_scalar(value: Any) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'
