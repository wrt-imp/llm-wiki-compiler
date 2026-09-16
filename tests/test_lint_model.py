"""LintIssue / LintResult tests."""

from __future__ import annotations

import json

from compiler.lint import (
    RULE_DEAD_LINK,
    RULE_ORPHAN_PAGE,
    RULE_SELF_LOOP,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    LintIssue,
    LintResult,
    count_issues,
    sort_issues,
)


def issue(rule: str, severity: str, path: str = "", message: str = "m") -> LintIssue:
    return LintIssue(rule=rule, severity=severity, message=message, path=path)


def test_issue_defaults_and_serialization() -> None:
    original = LintIssue(
        rule=RULE_DEAD_LINK,
        severity=SEVERITY_ERROR,
        message="a.md: link target 'missing.md' does not exist",
        path="a.md",
        object_id="abc",
        metadata={"target": "missing.md"},
    )

    restored = LintIssue.from_dict(json.loads(json.dumps(original.to_dict())))

    assert restored == original
    assert restored.metadata["target"] == "missing.md"


def test_sort_key_puts_errors_first_then_rule_then_path() -> None:
    error = issue(RULE_DEAD_LINK, SEVERITY_ERROR, "b.md")
    warning_a = issue(RULE_ORPHAN_PAGE, SEVERITY_WARNING, "a.md")
    warning_b = issue(RULE_ORPHAN_PAGE, SEVERITY_WARNING, "b.md")
    info = issue(RULE_SELF_LOOP, SEVERITY_INFO, "a.md")

    ordered = sort_issues([info, warning_b, error, warning_a])

    assert ordered == [error, warning_a, warning_b, info]


def test_sort_is_stable_for_identical_keys() -> None:
    first = LintIssue(rule="r", severity=SEVERITY_WARNING, message="m", metadata={"a": 1})
    second = LintIssue(rule="r", severity=SEVERITY_WARNING, message="m", metadata={"a": 1})

    assert sort_issues([first, second]) == [first, second]


def test_sort_uses_metadata_as_final_tie_breaker() -> None:
    first = LintIssue(rule="r", severity=SEVERITY_WARNING, message="m", metadata={"b": 1})
    second = LintIssue(rule="r", severity=SEVERITY_WARNING, message="m", metadata={"a": 1})

    assert sort_issues([first, second]) == [second, first]


def test_count_issues_reports_severities_categories_and_rules() -> None:
    issues = [
        issue(RULE_DEAD_LINK, SEVERITY_ERROR),
        issue(RULE_ORPHAN_PAGE, SEVERITY_WARNING),
        issue(RULE_ORPHAN_PAGE, SEVERITY_WARNING, path="b.md"),
        issue(RULE_SELF_LOOP, SEVERITY_INFO),
    ]

    counts = count_issues(issues)

    assert counts["errors"] == 1
    assert counts["warnings"] == 2
    assert counts["infos"] == 1
    assert counts["dead_links"] == 1
    assert counts["orphan_pages"] == 2
    assert counts["self_loops"] == 1
    assert counts["graph_problems"] == 0
    assert counts[RULE_ORPHAN_PAGE] == 2


def test_result_helpers() -> None:
    result = LintResult(
        issues=[
            issue(RULE_DEAD_LINK, SEVERITY_ERROR),
            issue(RULE_SELF_LOOP, SEVERITY_INFO),
        ],
        counts={"errors": 1},
        metadata={"linter_version": "test"},
    )

    assert result.is_clean() is False
    assert result.by_severity(SEVERITY_ERROR)[0].rule == RULE_DEAD_LINK
    assert result.by_rule(RULE_SELF_LOOP)[0].severity == SEVERITY_INFO
    assert result.rule_names() == [RULE_DEAD_LINK, RULE_SELF_LOOP]


def test_clean_result_when_only_info() -> None:
    result = LintResult(issues=[issue(RULE_SELF_LOOP, SEVERITY_INFO)])

    assert result.is_clean() is True


def test_result_round_trip() -> None:
    result = LintResult(
        issues=[issue(RULE_ORPHAN_PAGE, SEVERITY_WARNING, "a.md")],
        counts=count_issues([issue(RULE_ORPHAN_PAGE, SEVERITY_WARNING, "a.md")]),
        metadata={"linter_version": "linter-v1", "pages_checked": 3},
    )

    restored = LintResult.from_dict(json.loads(json.dumps(result.to_dict())))

    assert restored == result
