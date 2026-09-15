"""Candidate matching: which items *might* be the same knowledge object.

Only cheap, deterministic rules run here. The LLM is asked about the pairs
these rules produce - never about every possible pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Sequence, Tuple

from .normalize import alias_keys, compact_key, match_key, similarity, tokens

#: Minimum length ratio for "one name contains the other".
SUBSTRING_RATIO = 0.6
#: Minimum Jaccard overlap of word tokens.
TOKEN_OVERLAP = 0.5
#: Minimum character similarity for the near-miss rule.
SIMILARITY = 0.85
#: Default cap on semantic judgements per merge run.
DEFAULT_MAX_JUDGEMENTS = 200


@dataclass(frozen=True)
class CandidatePair:
    """Two item indices that should be judged, and why they were picked."""

    left: int
    right: int
    reason: str


def auto_merge_groups(items: Sequence[Any]) -> List[List[int]]:
    """Indices of items whose names normalize to exactly the same key.

    These are merged without asking a model: the names are literally the same
    once case, width, spacing and surrounding punctuation are normalized.
    """

    buckets: Dict[str, List[int]] = {}
    for index, item in enumerate(items):
        key = match_key(getattr(item, "name", ""))
        if key:
            buckets.setdefault(key, []).append(index)
    return [indices for indices in buckets.values() if len(indices) > 1]


def find_candidate_pairs(
    items: Sequence[Any],
    *,
    merged_groups: Sequence[Sequence[int]] = (),
    limit: int = DEFAULT_MAX_JUDGEMENTS,
) -> Tuple[List[CandidatePair], List[str]]:
    """Return the pairs worth a semantic judgement.

    Args:
        items: Entities or concepts (anything with ``name``/``aliases``).
        merged_groups: Groups that :func:`auto_merge_groups` already merged.
            Pairs inside one group are pointless to judge, but a group member
            can still be a useful bridge to an item outside the group.
        limit: Maximum number of pairs to return.

    Returns:
        The pairs, strongest rule first, plus warnings (for example when the
        limit cut the list short).
    """

    warnings: List[str] = []
    group_of: Dict[int, int] = {}
    for group_id, group in enumerate(merged_groups):
        for index in group:
            group_of[index] = group_id
    pairs: Dict[Tuple[int, int], CandidatePair] = {}

    def add(left: int, right: int, reason: str) -> None:
        if left == right:
            return
        left_group = group_of.get(left)
        if left_group is not None and left_group == group_of.get(right):
            return
        key = (min(left, right), max(left, right))
        if key not in pairs:
            pairs[key] = CandidatePair(key[0], key[1], reason)

    # 1. shared name or alias - the bridge across languages and spellings
    by_alias: Dict[str, List[int]] = {}
    for index, item in enumerate(items):
        for key in alias_keys(
            getattr(item, "name", ""), getattr(item, "aliases", ())
        ):
            by_alias.setdefault(key, []).append(index)
    for key, indices in by_alias.items():
        for position, left in enumerate(indices):
            for right in indices[position + 1 :]:
                add(left, right, f"shared name or alias {key!r}")

    # 2. the same name once whitespace is removed
    by_compact: Dict[str, List[int]] = {}
    for index, item in enumerate(items):
        key = compact_key(getattr(item, "name", ""))
        if key:
            by_compact.setdefault(key, []).append(index)
    for indices in by_compact.values():
        for position, left in enumerate(indices):
            for right in indices[position + 1 :]:
                add(left, right, "same name without whitespace")

    # 3. same first or last character: containment, tokens, near spellings
    for left, right in _blocked_pairs(items):
        left_key = compact_key(getattr(items[left], "name", ""))
        right_key = compact_key(getattr(items[right], "name", ""))
        if not left_key or not right_key:
            continue
        short, long = sorted((left_key, right_key), key=len)
        if short != long and short in long and len(short) / len(long) >= SUBSTRING_RATIO:
            add(left, right, "one name contains the other")
            continue
        overlap = _token_overlap(
            getattr(items[left], "name", ""), getattr(items[right], "name", "")
        )
        if overlap >= TOKEN_OVERLAP:
            add(left, right, f"token overlap {overlap:.2f}")
            continue
        ratio = similarity(
            getattr(items[left], "name", ""), getattr(items[right], "name", "")
        )
        if ratio >= SIMILARITY:
            add(left, right, f"names are {ratio:.2f} similar")

    ordered = list(pairs.values())
    if limit is not None and len(ordered) > limit:
        warnings.append(
            f"candidate pairs truncated to {limit} (of {len(ordered)}); "
            "raise max_judgements to judge more"
        )
        ordered = ordered[:limit]
    return ordered, warnings


def _blocked_pairs(items: Sequence[Any]) -> Iterator[Tuple[int, int]]:
    """Pairs sharing a first/last character or one word token.

    This is the cheap blocking step that keeps the rules below away from all
    pairs: word order differences ("Graph Knowledge" / "Knowledge Graph") are
    caught by the token bucket, not by character buckets.
    """

    buckets: Dict[str, List[int]] = {}
    for index, item in enumerate(items):
        name = getattr(item, "name", "")
        key = compact_key(name)
        if key:
            buckets.setdefault("^" + key[0], []).append(index)
            buckets.setdefault(key[-1] + "$", []).append(index)
        for token in sorted(tokens(name)):
            buckets.setdefault("#" + token, []).append(index)

    seen = set()
    for indices in buckets.values():
        for position, left in enumerate(indices):
            for right in indices[position + 1 :]:
                pair = (min(left, right), max(left, right))
                if pair not in seen:
                    seen.add(pair)
                    yield pair


def _token_overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = tokens(left), tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0
