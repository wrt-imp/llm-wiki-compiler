"""Stage 9 of the LLM Wiki Compiler: Lint.

Reports structure and quality problems of an already compiled wiki::

    >>> from compiler.lint import lint
    >>> result = lint(knowledge_base, wiki_build=build, link_result=links, graph=graph)
    >>> result.is_clean()
    False
    >>> result.counts["dead_links"]
    0

Lint only reads: it never modifies the KnowledgeBase, the wiki files, the graph
or the link result, it never re-parses sources and it never rebuilds anything.
Issues are ordered deterministically, so the same input always gives the same
report.
"""

from .linter import lint
from .model import (
    LINTER_VERSION,
    RULES,
    RULE_AMBIGUOUS_NAME,
    RULE_DANGLING_EDGE,
    RULE_DEAD_LINK,
    RULE_ISOLATED_NODE,
    RULE_MISSING_SOURCE,
    RULE_ORPHAN_PAGE,
    RULE_SELF_LOOP,
    RULE_SEVERITIES,
    RULE_UNINDEXED_PAGE,
    RULE_UNLINKED_FACT,
    RULE_UNLINKED_RELATION,
    SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    LintIssue,
    LintResult,
    canonical_metadata,
    count_issues,
    sort_issues,
)
from .rules import (
    PageText,
    lint_graph,
    lint_knowledge,
    lint_links,
    lint_pages,
    lint_sources,
)

__all__ = [
    "LINTER_VERSION",
    "LintIssue",
    "LintResult",
    "PageText",
    "RULES",
    "RULE_AMBIGUOUS_NAME",
    "RULE_DANGLING_EDGE",
    "RULE_DEAD_LINK",
    "RULE_ISOLATED_NODE",
    "RULE_MISSING_SOURCE",
    "RULE_ORPHAN_PAGE",
    "RULE_SELF_LOOP",
    "RULE_SEVERITIES",
    "RULE_UNINDEXED_PAGE",
    "RULE_UNLINKED_FACT",
    "RULE_UNLINKED_RELATION",
    "SEVERITIES",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "canonical_metadata",
    "count_issues",
    "lint",
    "lint_graph",
    "lint_knowledge",
    "lint_links",
    "lint_pages",
    "lint_sources",
    "sort_issues",
]
