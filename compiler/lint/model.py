"""Issues found by the linter and the result of a lint run.

Two severities carry meaning - ``error`` for broken structure, ``warning`` for
quality problems - plus ``info`` for things that are explicitly allowed, such
as a self loop edge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Bumped whenever the checks change; stored in ``LintResult.metadata``.
LINTER_VERSION = "linter-v1"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)

_SEVERITY_RANK = {
    SEVERITY_ERROR: 0,
    SEVERITY_WARNING: 1,
    SEVERITY_INFO: 2,
}

#: Rule names, in the order the checks are described.
RULE_DEAD_LINK = "dead_link"
RULE_ORPHAN_PAGE = "orphan_page"
RULE_MISSING_SOURCE = "missing_source"
RULE_UNLINKED_FACT = "unlinked_fact"
RULE_UNLINKED_RELATION = "unlinked_relation"
RULE_AMBIGUOUS_NAME = "ambiguous_name"
RULE_DANGLING_EDGE = "dangling_edge"
RULE_ISOLATED_NODE = "isolated_node"
RULE_SELF_LOOP = "self_loop"
RULE_UNINDEXED_PAGE = "unindexed_page"

RULES = (
    RULE_DEAD_LINK,
    RULE_ORPHAN_PAGE,
    RULE_MISSING_SOURCE,
    RULE_UNLINKED_FACT,
    RULE_UNLINKED_RELATION,
    RULE_AMBIGUOUS_NAME,
    RULE_DANGLING_EDGE,
    RULE_ISOLATED_NODE,
    RULE_SELF_LOOP,
    RULE_UNINDEXED_PAGE,
)

#: Severity per rule: structure breaks are errors, quality issues warnings.
RULE_SEVERITIES = {
    RULE_DEAD_LINK: SEVERITY_ERROR,
    RULE_DANGLING_EDGE: SEVERITY_ERROR,
    RULE_ORPHAN_PAGE: SEVERITY_WARNING,
    RULE_MISSING_SOURCE: SEVERITY_WARNING,
    RULE_UNLINKED_FACT: SEVERITY_WARNING,
    RULE_UNLINKED_RELATION: SEVERITY_WARNING,
    RULE_AMBIGUOUS_NAME: SEVERITY_WARNING,
    RULE_ISOLATED_NODE: SEVERITY_WARNING,
    RULE_UNINDEXED_PAGE: SEVERITY_WARNING,
    RULE_SELF_LOOP: SEVERITY_INFO,
}


@dataclass(frozen=True)
class LintIssue:
    """One finding."""

    rule: str
    severity: str
    message: str
    path: str = ""
    object_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def sort_key(self) -> Tuple[int, str, str, str, str, str]:
        """Total order: severity first, then rule, page, object, message."""

        return (
            _SEVERITY_RANK.get(self.severity, len(SEVERITIES)),
            self.rule,
            self.path,
            self.object_id,
            self.message,
            canonical_metadata(self.metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "object_id": self.object_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LintIssue":
        return cls(
            rule=data["rule"],
            severity=data["severity"],
            message=data["message"],
            path=data.get("path", ""),
            object_id=data.get("object_id", ""),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class LintResult:
    """Everything a lint run found."""

    issues: List[LintIssue] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_clean(self) -> bool:
        """``True`` when there is no error and no warning."""

        return not self.by_severity(SEVERITY_ERROR) and not self.by_severity(
            SEVERITY_WARNING
        )

    def by_severity(self, severity: str) -> List[LintIssue]:
        return [issue for issue in self.issues if issue.severity == severity]

    def by_rule(self, rule: str) -> List[LintIssue]:
        return [issue for issue in self.issues if issue.rule == rule]

    def rule_names(self) -> List[str]:
        """Rule names that produced at least one issue, in report order."""

        seen: List[str] = []
        for issue in self.issues:
            if issue.rule not in seen:
                seen.append(issue.rule)
        return seen

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "counts": dict(self.counts),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LintResult":
        return cls(
            issues=[LintIssue.from_dict(item) for item in data.get("issues", [])],
            counts=dict(data.get("counts", {})),
            metadata=dict(data.get("metadata", {})),
        )


def canonical_metadata(metadata: Dict[str, Any]) -> str:
    """Stable string form of issue metadata, used as the final sort key."""

    return json.dumps(metadata, sort_keys=True, ensure_ascii=False, default=str)


def sort_issues(issues: Sequence[LintIssue]) -> List[LintIssue]:
    """Sort issues so the report is always in the same order."""

    return sorted(issues, key=lambda issue: issue.sort_key)


def count_issues(issues: Sequence[LintIssue]) -> Dict[str, int]:
    """Severity totals, category totals and per rule counts."""

    counts: Dict[str, int] = {severity + "s": 0 for severity in SEVERITIES}
    for severity in SEVERITIES:
        counts[severity + "s"] = sum(
            1 for issue in issues if issue.severity == severity
        )
    for rule in RULES:
        counts[rule] = sum(1 for issue in issues if issue.rule == rule)

    counts["orphan_pages"] = counts[RULE_ORPHAN_PAGE]
    counts["dead_links"] = counts[RULE_DEAD_LINK]
    counts["missing_sources"] = counts[RULE_MISSING_SOURCE]
    counts["ambiguous_names"] = counts[RULE_AMBIGUOUS_NAME]
    counts["unlinked_facts"] = counts[RULE_UNLINKED_FACT]
    counts["unlinked_relations"] = counts[RULE_UNLINKED_RELATION]
    counts["graph_problems"] = counts[RULE_DANGLING_EDGE] + counts[RULE_ISOLATED_NODE]
    counts["self_loops"] = counts[RULE_SELF_LOOP]
    counts["unindexed_pages"] = counts[RULE_UNINDEXED_PAGE]
    return counts
