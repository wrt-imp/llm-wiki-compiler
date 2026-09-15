"""Semantic Merge: several Knowledge IRs in, one KnowledgeBase out.

Four stages:

1. Normalize          - names/statements get stable keys (pure code, no LLM)
2. Candidate Matching - cheap rules pick the pairs worth judging
3. Semantic Judge     - the LLM answers ``{"same": bool, "reason": str}``
4. Merge              - canonical name, merged descriptions and sources,
                        duplicate facts and relations removed

The input is always existing Knowledge IRs: nothing is re-parsed and nothing is
re-extracted. Provenance is never dropped - every merged item keeps the union of
the source references it came in with.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..extraction.errors import InvalidResponseError
from ..knowledge import (
    ENTITY_TYPE_OTHER,
    KIND_CONCEPT,
    KIND_ENTITY,
    Concept,
    Entity,
    Fact,
    KnowledgeBase,
    KnowledgeIR,
    Relation,
    SourceRef,
)
from ..llm import LLMError
from .candidates import (
    DEFAULT_MAX_JUDGEMENTS,
    CandidatePair,
    auto_merge_groups,
    find_candidate_pairs,
)
from .errors import InvalidJudgeResponseError
from .judge import JudgeVerdict, SemanticJudge
from .normalize import alias_keys, match_key, statement_key

#: Values accepted by ``on_judge_error``.
ON_ERROR_SKIP = "skip"
ON_ERROR_RAISE = "raise"

#: Judge failures that "skip" mode tolerates and reports as warnings.
JUDGE_ERRORS = (InvalidResponseError, InvalidJudgeResponseError, LLMError)


class Merger:
    """Merge several Knowledge IRs into one :class:`KnowledgeBase`."""

    def __init__(
        self,
        judge: Optional[SemanticJudge] = None,
        *,
        on_judge_error: str = ON_ERROR_SKIP,
        max_judgements: int = DEFAULT_MAX_JUDGEMENTS,
    ) -> None:
        if on_judge_error not in (ON_ERROR_SKIP, ON_ERROR_RAISE):
            raise ValueError(
                "on_judge_error must be 'skip' or 'raise', got "
                f"{on_judge_error!r}"
            )
        self.judge = judge
        self.on_judge_error = on_judge_error
        self.max_judgements = max_judgements

    def merge(self, knowledge_irs: Iterable[KnowledgeIR]) -> KnowledgeBase:
        """Merge the knowledge extracted from several documents."""

        irs = list(knowledge_irs)
        state = _MergeState()

        entities, entity_ids, entity_names = self._merge_kind(
            KIND_ENTITY, [entity for ir in irs for entity in ir.entities], state
        )
        concepts, concept_ids, concept_names = self._merge_kind(
            KIND_CONCEPT, [concept for ir in irs for concept in ir.concepts], state
        )

        id_map = {**entity_ids, **concept_ids}
        name_map = {**entity_names, **concept_names}
        id_by_key: Dict[str, str] = {}
        for item in [*entities, *concepts]:
            for key in alias_keys(item.name, item.aliases):
                id_by_key.setdefault(key, item.id)

        facts = _dedupe_facts([fact for ir in irs for fact in ir.facts], name_map)
        relations = _dedupe_relations(
            [relation for ir in irs for relation in ir.relations],
            id_map,
            name_map,
            id_by_key,
        )
        documents = _collect_documents(irs)

        metadata: Dict[str, Any] = {
            "input_knowledge_irs": len(irs),
            "documents": len(documents),
            "merges": state.merges,
            "judged_pairs": state.judged_pairs,
            "judged_same": sum(1 for verdict in state.verdicts if verdict["same"]),
            "judge_failures": state.judge_failures,
            "judge_model": _judge_model(self.judge),
            "judge_prompt_version": getattr(self.judge, "prompt_version", None),
            "warnings": state.warnings,
            "counts": {
                "entities": len(entities),
                "concepts": len(concepts),
                "facts": len(facts),
                "relations": len(relations),
            },
        }
        return KnowledgeBase(
            entities=entities,
            concepts=concepts,
            facts=facts,
            relations=relations,
            documents=documents,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Per kind merging
    # ------------------------------------------------------------------
    def _merge_kind(
        self, kind: str, items: Sequence[Any], state: "_MergeState"
    ) -> Tuple[List[Any], Dict[str, str], Dict[str, str]]:
        if not items:
            return [], {}, {}

        auto_groups = auto_merge_groups(items)
        pairs, pair_warnings = find_candidate_pairs(
            items, merged_groups=auto_groups, limit=self.max_judgements
        )
        state.warnings.extend(pair_warnings)
        if self.judge is None and pairs:
            state.warnings.append(
                f"{len(pairs)} candidate pair(s) of {kind} were not judged: "
                "no judge configured"
            )

        groups = _UnionFind(len(items))
        for group in auto_groups:
            for index in group[1:]:
                groups.union(group[0], index)
        if self.judge is not None:
            for pair in pairs:
                verdict = self._judge_pair(kind, pair, items, state)
                if verdict is not None and verdict.same:
                    groups.union(pair.left, pair.right)

        buckets: Dict[int, List[int]] = {}
        for index in range(len(items)):
            buckets.setdefault(groups.find(index), []).append(index)

        merged_items: List[Any] = []
        id_map: Dict[str, str] = {}
        name_map: Dict[str, str] = {}
        for members in sorted(buckets.values(), key=min):
            member_items = [items[index] for index in members]
            canonical = _merge_items(kind, member_items)
            merged_items.append(canonical)
            for item in member_items:
                if item.id:
                    id_map[item.id] = canonical.id
                for key in alias_keys(item.name, item.aliases):
                    name_map.setdefault(key, canonical.name)
            if len(member_items) > 1:
                state.merges.append(
                    _merge_record(kind, member_items, canonical, members, state)
                )
        return merged_items, id_map, name_map

    def _judge_pair(
        self,
        kind: str,
        pair: CandidatePair,
        items: Sequence[Any],
        state: "_MergeState",
    ) -> Optional[JudgeVerdict]:
        left, right = items[pair.left], items[pair.right]
        memo_key = (kind, match_key(left.name), match_key(right.name))
        if memo_key in state.memo:
            return state.memo[memo_key]

        state.judged_pairs += 1
        try:
            verdict = self.judge.judge(kind, left, right)  # type: ignore[union-attr]
        except JUDGE_ERRORS as error:
            state.judge_failures.append(
                f"{kind} {left.name!r} ~ {right.name!r}: {error}"
            )
            if self.on_judge_error == ON_ERROR_RAISE:
                raise
            state.warnings.append(
                f"judge failed for {kind} {left.name!r} ~ {right.name!r}: {error}"
            )
            return None

        state.memo[memo_key] = verdict
        state.verdicts.append(
            {
                "kind": kind,
                "names": [left.name, right.name],
                "same": verdict.same,
                "rule": pair.reason,
                "reason": verdict.reason,
            }
        )
        return verdict


def merge_knowledge_bases(
    knowledge_irs: Iterable[KnowledgeIR],
    judge: Optional[SemanticJudge] = None,
    *,
    on_judge_error: str = ON_ERROR_SKIP,
    max_judgements: int = DEFAULT_MAX_JUDGEMENTS,
) -> KnowledgeBase:
    """Convenience wrapper around :class:`Merger`."""

    return Merger(
        judge, on_judge_error=on_judge_error, max_judgements=max_judgements
    ).merge(knowledge_irs)


# ----------------------------------------------------------------------
# Merging a group of items
# ----------------------------------------------------------------------
def _merge_items(kind: str, members: Sequence[Any]) -> Any:
    canonical_name = _canonical_name(members)
    aliases = _union_aliases(members, canonical_name)
    description = _merge_descriptions(member.description for member in members)
    sources = merge_sources(member.sources for member in members)
    # Merged groups get the id derived from the canonical name; a single item
    # keeps the id it came in with.
    item_id = members[0].id if len(members) == 1 else ""

    if kind == KIND_CONCEPT:
        return Concept(
            name=canonical_name,
            description=description,
            aliases=aliases,
            sources=sources,
            id=item_id,
        )
    return Entity(
        name=canonical_name,
        type=_merge_types(member.type for member in members),
        description=description,
        aliases=aliases,
        sources=sources,
        id=item_id,
    )


def _canonical_name(members: Sequence[Any]) -> str:
    """Most frequent spelling, then the best evidenced, then the earliest."""

    counts: Counter = Counter()
    evidence: Dict[str, int] = {}
    first_index: Dict[str, int] = {}
    original: Dict[str, str] = {}
    for index, item in enumerate(members):
        key = match_key(item.name)
        if not key:
            continue
        counts[key] += 1
        evidence[key] = evidence.get(key, 0) + len(item.sources)
        first_index.setdefault(key, index)
        original.setdefault(key, item.name.strip())

    if not counts:
        return members[0].name
    best = max(
        counts, key=lambda key: (counts[key], evidence[key], -first_index[key])
    )
    return original[best]


def _merge_types(types: Iterable[str]) -> str:
    """Most common specific entity type; "other" only when nothing else exists."""

    candidates = [
        str(value).strip()
        for value in types
        if value and str(value).strip() and str(value).strip() != ENTITY_TYPE_OTHER
    ]
    if not candidates:
        return ENTITY_TYPE_OTHER
    counts: Counter = Counter(candidates)
    first_index: Dict[str, int] = {}
    for index, value in enumerate(candidates):
        first_index.setdefault(value, index)
    return max(counts, key=lambda value: (counts[value], -first_index[value]))


def _union_aliases(members: Sequence[Any], canonical_name: str) -> List[str]:
    """Every other spelling stays reachable as an alias."""

    result: List[str] = []
    seen = {match_key(canonical_name)}
    for item in members:
        for name in [item.name, *item.aliases]:
            cleaned = str(name).strip()
            key = match_key(cleaned)
            if cleaned and key and key not in seen:
                seen.add(key)
                result.append(cleaned)
    return result


def _merge_descriptions(descriptions: Iterable[str]) -> str:
    """Distinct descriptions, joined with newlines so nothing is dropped."""

    parts: List[str] = []
    seen = set()
    for description in descriptions:
        cleaned = str(description or "").strip()
        key = match_key(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            parts.append(cleaned)
    return "\n".join(parts)


def merge_sources(groups: Iterable[Iterable[SourceRef]]) -> List[SourceRef]:
    """Union of source references, de-duplicated, order preserved.

    This is what makes merging lossless: sources are only ever added.
    """

    result: List[SourceRef] = []
    seen = set()
    for group in groups:
        for reference in group:
            key = (
                reference.document_id,
                reference.section_id,
                reference.page_number,
                reference.quote,
            )
            if key not in seen:
                seen.add(key)
                result.append(reference)
    return result


def _merge_record(
    kind: str,
    members: Sequence[Any],
    canonical: Any,
    indices: Sequence[int],
    state: "_MergeState",
) -> Dict[str, Any]:
    """Audit trail entry for one merged group."""

    reasons = [
        verdict["reason"]
        for verdict in state.verdicts
        if verdict["kind"] == kind and verdict["same"]
        and _verdict_names_in_group(verdict, members)
    ]
    same_key = len({match_key(member.name) for member in members}) == 1
    return {
        "kind": kind,
        "names": [member.name for member in members],
        "canonical": canonical.name,
        "method": "normalized-name" if same_key else "llm",
        "reasons": [reason for reason in reasons if reason],
        "sources": len(canonical.sources),
    }


def _verdict_names_in_group(verdict: Dict[str, Any], members: Sequence[Any]) -> bool:
    names = {match_key(member.name) for member in members}
    return all(match_key(name) in names for name in verdict["names"])


# ----------------------------------------------------------------------
# Facts and relations
# ----------------------------------------------------------------------
def _dedupe_facts(
    facts: Sequence[Fact], name_map: Dict[str, str]
) -> List[Fact]:
    result: List[Fact] = []
    merged: Dict[str, Fact] = {}
    for fact in facts:
        canonical = _canonicalize_fact(fact, name_map)
        key = statement_key(canonical.statement) or canonical.id
        existing = merged.get(key)
        if existing is None:
            merged[key] = canonical
            result.append(canonical)
        else:
            existing.sources = merge_sources([existing.sources, canonical.sources])
    return result


def _canonicalize_fact(fact: Fact, name_map: Dict[str, str]) -> Fact:
    """Copy of the fact with subject/object pointing at canonical names."""

    return Fact(
        statement=fact.statement,
        subject=_canonicalize_name(fact.subject, name_map),
        predicate=fact.predicate,
        object=_canonicalize_name(fact.object, name_map),
        sources=list(fact.sources),
        id=fact.id,
    )


def _dedupe_relations(
    relations: Sequence[Relation],
    id_map: Dict[str, str],
    name_map: Dict[str, str],
    id_by_key: Dict[str, str],
) -> List[Relation]:
    result: List[Relation] = []
    merged: Dict[Tuple[str, str, str], Relation] = {}
    for relation in relations:
        source_name = _canonicalize_name(relation.source, name_map)
        target_name = _canonicalize_name(relation.target, name_map)
        source_id = id_by_key.get(match_key(source_name)) or id_map.get(
            relation.source_id or ""
        )
        target_id = id_by_key.get(match_key(target_name)) or id_map.get(
            relation.target_id or ""
        )
        canonical = Relation(
            source=source_name,
            target=target_name,
            type=relation.type,
            description=relation.description,
            source_id=source_id,
            target_id=target_id,
            sources=list(relation.sources),
        )
        key = (
            match_key(source_name),
            match_key(relation.type),
            match_key(target_name),
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = canonical
            result.append(canonical)
            continue
        existing.sources = merge_sources([existing.sources, canonical.sources])
        existing.description = _merge_descriptions(
            [existing.description, canonical.description]
        )
        if existing.source_id is None:
            existing.source_id = canonical.source_id
        if existing.target_id is None:
            existing.target_id = canonical.target_id
    return result


def _canonicalize_name(value: str, name_map: Dict[str, str]) -> str:
    if not value:
        return value
    return name_map.get(match_key(value), value)


def _collect_documents(irs: Sequence[KnowledgeIR]) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []
    seen = set()
    for ir in irs:
        if not ir.document_id or ir.document_id in seen:
            continue
        seen.add(ir.document_id)
        documents.append(
            {
                "id": ir.document_id,
                "title": ir.document_title,
                "source": ir.source,
            }
        )
    return documents


def _judge_model(judge: Optional[SemanticJudge]) -> Optional[str]:
    if judge is None:
        return None
    model = getattr(getattr(judge, "client", None), "model", None)
    return model or getattr(judge, "model", None) or type(judge).__name__


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
class _UnionFind:
    """Tiny union-find: pairs judged "same" end up in one group."""

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, index: int) -> int:
        parent = self._parent
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:
            parent[index], index = root, parent[index]
        return root

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[right_root] = left_root


@dataclass
class _MergeState:
    """Bookkeeping for one merge run (audit trail and warnings)."""

    warnings: List[str] = field(default_factory=list)
    merges: List[Dict[str, Any]] = field(default_factory=list)
    verdicts: List[Dict[str, Any]] = field(default_factory=list)
    judge_failures: List[str] = field(default_factory=list)
    memo: Dict[Tuple[str, str, str], JudgeVerdict] = field(default_factory=dict)
    judged_pairs: int = 0
