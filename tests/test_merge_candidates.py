"""Candidate matching tests: cheap rules, never all pairs."""

from __future__ import annotations

from compiler.merge import auto_merge_groups, find_candidate_pairs
from support import concept, entity


def test_auto_merge_groups_by_normalized_name() -> None:
    items = [
        entity("\u89e3\u6790\u5668"),
        entity("\u6587\u6863\u6a21\u578b"),
        entity("  \u89e3\u6790\u5668  "),
    ]

    assert auto_merge_groups(items) == [[0, 2]]


def test_auto_merge_ignores_unrelated_names() -> None:
    items = [entity("\u89e3\u6790\u5668"), entity("\u6587\u6863\u6a21\u578b")]

    assert auto_merge_groups(items) == []


def test_candidates_are_empty_for_unrelated_names() -> None:
    items = [entity("\u89e3\u6790\u5668"), entity("\u6587\u6863\u6a21\u578b")]

    pairs, warnings = find_candidate_pairs(items)

    assert pairs == []
    assert warnings == []


def test_shared_alias_makes_a_candidate() -> None:
    items = [
        entity("\u89e3\u6790\u5668", aliases=("Parser",)),
        entity("Parser"),
    ]

    pairs, _ = find_candidate_pairs(items)

    assert [pair.reason for pair in pairs] == ["shared name or alias 'parser'"]
    assert (pairs[0].left, pairs[0].right) == (0, 1)


def test_shared_alias_works_for_concepts_too() -> None:
    items = [
        concept("\u77e5\u8bc6\u56fe\u8c31", aliases=("Knowledge Graph",)),
        concept("knowledge graph"),
    ]

    pairs, _ = find_candidate_pairs(items)

    assert len(pairs) == 1


def test_whitespace_only_difference_is_a_candidate() -> None:
    items = [entity("Document Model"), entity("DocumentModel")]

    pairs, _ = find_candidate_pairs(items)

    assert len(pairs) == 1


def test_one_name_containing_the_other_is_a_candidate() -> None:
    items = [entity("Document Model"), entity("Document Model v2")]

    pairs, _ = find_candidate_pairs(items)

    assert [pair.reason for pair in pairs] == ["one name contains the other"]


def test_short_substrings_are_not_candidates() -> None:
    # "解析器" is contained in "知识图谱编译器" but is far too short to be useful.
    items = [entity("\u89e3\u6790\u5668"), entity("\u77e5\u8bc6\u56fe\u8c31\u7f16\u8bd1\u5668")]

    pairs, _ = find_candidate_pairs(items)

    assert pairs == []


def test_token_overlap_is_a_candidate() -> None:
    items = [entity("Graph Knowledge"), entity("Knowledge Graph")]

    pairs, _ = find_candidate_pairs(items)

    assert [pair.reason for pair in pairs] == ["token overlap 1.00"]


def test_near_spellings_are_candidates() -> None:
    items = [entity("parser"), entity("parseer")]

    pairs, _ = find_candidate_pairs(items)

    assert len(pairs) == 1
    assert pairs[0].reason.startswith("names are ")


def test_plural_forms_are_candidates() -> None:
    items = [entity("parser"), entity("parsers")]

    pairs, _ = find_candidate_pairs(items)

    assert [pair.reason for pair in pairs] == ["one name contains the other"]


def test_pairs_already_auto_merged_are_skipped() -> None:
    items = [entity("Parser"), entity(" parser ")]

    pairs, _ = find_candidate_pairs(items, merged_groups=[[0, 1]])

    assert pairs == []


def test_a_merged_group_can_still_bridge_to_an_outsider() -> None:
    items = [
        entity("解析器"),
        entity("解析器"),
        entity("Parser", aliases=("解析器",)),
    ]

    pairs, _ = find_candidate_pairs(items, merged_groups=[[0, 1]])

    assert [(pair.left, pair.right) for pair in pairs] == [(0, 2), (1, 2)]


def test_candidate_limit_is_reported() -> None:
    items = [entity("parser"), entity("parsers"), entity("parser1")]

    pairs, warnings = find_candidate_pairs(items, limit=1)

    assert len(pairs) == 1
    assert any("truncated to 1" in warning for warning in warnings)
