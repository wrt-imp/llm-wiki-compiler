"""Run the checks and collect the report.

Only the results the caller passes in are used. Nothing is written, nothing is
rebuilt, and the same input always produces the same report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..graph import Graph
from ..knowledge import KnowledgeBase
from ..linker import LinkResult
from ..search import SearchIndex
from ..wiki import WikiBuild
from .model import (
    LINTER_VERSION,
    RULE_AMBIGUOUS_NAME,
    RULE_DANGLING_EDGE,
    RULE_DEAD_LINK,
    RULE_ISOLATED_NODE,
    RULE_MISSING_SOURCE,
    RULE_ORPHAN_PAGE,
    RULE_SELF_LOOP,
    RULE_UNINDEXED_PAGE,
    RULE_UNLINKED_FACT,
    RULE_UNLINKED_RELATION,
    LintIssue,
    LintResult,
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


def lint(
    knowledge_base: Optional[KnowledgeBase] = None,
    *,
    wiki_build: Optional[WikiBuild] = None,
    link_result: Optional[LinkResult] = None,
    graph: Optional[Graph] = None,
    search_index: Optional[SearchIndex] = None,
) -> LintResult:
    """Check the compiled results and report what looks wrong.

    Args:
        knowledge_base: Used for the missing source check.
        wiki_build: Page list and output directory, used for link/page checks.
        link_result: Alternative source for the page list, plus its ambiguity
            report.
        graph: Used for unlinked facts/relations, dangling edges, isolated
            nodes and self loops.
        search_index: Used only to notice pages that are not indexed.

    Returns:
        A :class:`LintResult` with deterministically ordered issues.

    Raises:
        ValueError: when no input at all is given.
    """

    if all(
        item is None
        for item in (knowledge_base, wiki_build, link_result, graph, search_index)
    ):
        raise ValueError(
            "lint needs at least one input (knowledge_base, wiki_build, "
            "link_result, graph, search_index)"
        )

    warnings: List[str] = []
    ran: List[str] = []
    skipped: List[str] = []
    issues: List[LintIssue] = []

    pages, root = _collect_pages(wiki_build, link_result, warnings)
    page_paths = _object_page_paths(wiki_build)

    if pages:
        issues.extend(lint_links(pages, root=root))
        ran.append(RULE_DEAD_LINK)
        issues.extend(
            lint_pages(pages, root=root, search_index=search_index)
        )
        ran.extend([RULE_ORPHAN_PAGE, RULE_UNINDEXED_PAGE])
        if search_index is None:
            skipped.append(RULE_UNINDEXED_PAGE)
    else:
        skipped.extend([RULE_DEAD_LINK, RULE_ORPHAN_PAGE, RULE_UNINDEXED_PAGE])

    if knowledge_base is not None:
        issues.extend(lint_sources(knowledge_base, page_paths=page_paths))
        ran.append(RULE_MISSING_SOURCE)
    else:
        skipped.append(RULE_MISSING_SOURCE)

    if graph is not None or link_result is not None:
        issues.extend(
            lint_knowledge(
                graph=graph, link_result=link_result, page_paths=page_paths
            )
        )
        ran.append(RULE_AMBIGUOUS_NAME)
        if graph is not None:
            ran.extend([RULE_UNLINKED_FACT, RULE_UNLINKED_RELATION])
        else:
            skipped.extend([RULE_UNLINKED_FACT, RULE_UNLINKED_RELATION])
    else:
        skipped.extend(
            [RULE_UNLINKED_FACT, RULE_UNLINKED_RELATION, RULE_AMBIGUOUS_NAME]
        )

    if graph is not None:
        issues.extend(lint_graph(graph, page_paths=page_paths))
        ran.extend([RULE_DANGLING_EDGE, RULE_ISOLATED_NODE, RULE_SELF_LOOP])
    else:
        skipped.extend([RULE_DANGLING_EDGE, RULE_ISOLATED_NODE, RULE_SELF_LOOP])

    ordered = sort_issues(issues)
    metadata: Dict[str, Any] = {
        "linter_version": LINTER_VERSION,
        "inputs": {
            "knowledge_base": knowledge_base is not None,
            "wiki_build": wiki_build is not None,
            "link_result": link_result is not None,
            "graph": graph is not None,
            "search_index": search_index is not None,
        },
        "pages_checked": len(pages),
        "files_read": [page.path for page in pages],
        "rules_run": sorted(set(ran)),
        "skipped_rules": sorted(set(skipped) - set(ran)),
        "warnings": warnings,
        "link_result_dead_links": (
            link_result.counts.get("dead_links") if link_result is not None else None
        ),
        "graph_declared_self_loops": (
            graph.metadata.get("self_loops") if graph is not None else None
        ),
    }
    return LintResult(issues=ordered, counts=count_issues(ordered), metadata=metadata)


def _collect_pages(
    wiki_build: Optional[WikiBuild],
    link_result: Optional[LinkResult],
    warnings: List[str],
) -> Tuple[List[PageText], Optional[Path]]:
    """Read the wiki pages that should be checked (never the sources)."""

    root: Optional[Path] = None
    files: List[str] = []
    kinds: Dict[str, str] = {}

    if wiki_build is not None:
        root = Path(wiki_build.output_dir)
        files = list(wiki_build.written) or [page.path for page in wiki_build.pages]
        kinds = {page.path: page.kind for page in wiki_build.pages}
    elif link_result is not None:
        root = Path(link_result.output_dir)
        files = list(link_result.files)

    pages: List[PageText] = []
    for relative in dict.fromkeys(files):
        text = ""
        if root is not None:
            try:
                text = (root / relative).read_text(encoding="utf-8")
            except OSError as exc:
                warnings.append(f"{relative}: cannot read page ({exc})")
        pages.append(
            PageText(path=relative, text=text, kind=kinds.get(relative, ""))
        )
    return pages, root


def _object_page_paths(wiki_build: Optional[WikiBuild]) -> Dict[str, str]:
    if wiki_build is None:
        return {}
    return {
        page.object_id: page.path
        for page in wiki_build.pages
        if page.object_id
    }
