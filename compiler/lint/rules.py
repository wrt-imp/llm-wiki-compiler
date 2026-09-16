"""The individual checks.

Every function reads results that were already built (a KnowledgeBase, a
WikiBuild, a LinkResult, a Graph, a SearchIndex) and returns issues. Nothing is
rebuilt here: no link resolution, no graph construction, no searching.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..graph import Graph
from ..knowledge import KnowledgeBase
from ..linker import find_link_targets
from ..merge.normalize import match_key
from .model import (
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
    LintIssue,
)

#: Longest object label repeated in an issue message.
MAX_LABEL_CHARS = 80


@dataclass(frozen=True)
class PageText:
    """One wiki page as the linter sees it."""

    path: str
    text: str
    kind: str = ""


def lint_links(
    pages: Sequence[PageText],
    *,
    root: Optional[Any] = None,
    index_name: str = "index",
) -> List[LintIssue]:
    """Dead links: every markdown link must point at a file that exists."""

    issues: List[LintIssue] = []
    known = {page.path for page in pages}
    for page in pages:
        for target in find_link_targets(page.text):
            if _is_external(target):
                continue
            resolved = _resolve(page.path, target)
            if resolved in known:
                continue
            if root is not None and (Path(root) / resolved).is_file():
                continue
            issues.append(
                LintIssue(
                    rule=RULE_DEAD_LINK,
                    severity=RULE_SEVERITIES[RULE_DEAD_LINK],
                    message=f"{page.path}: link target {target!r} does not exist",
                    path=page.path,
                    metadata={"target": target},
                )
            )
    return issues


def lint_pages(
    pages: Sequence[PageText],
    *,
    root: Optional[Any] = None,
    index_name: str = "index",
    search_index: Optional[Any] = None,
) -> List[LintIssue]:
    """Orphan pages and pages missing from the search index."""

    issues: List[LintIssue] = []
    index_paths = {page.path for page in pages if _is_index(page, index_name)}
    page_paths = {page.path for page in pages}
    incoming: Dict[str, List[str]] = {path: [] for path in page_paths}

    for page in pages:
        # links written by the index do not count as knowledge links
        if page.path in index_paths:
            continue
        for target in find_link_targets(page.text):
            if _is_external(target):
                continue
            resolved = _resolve(page.path, target)
            if resolved in page_paths and resolved not in index_paths:
                incoming.setdefault(resolved, []).append(page.path)

    for page in pages:
        if page.path in index_paths:
            continue
        if not incoming.get(page.path):
            issues.append(
                LintIssue(
                    rule=RULE_ORPHAN_PAGE,
                    severity=RULE_SEVERITIES[RULE_ORPHAN_PAGE],
                    message=(
                        f"{page.path}: no incoming link from another "
                        "knowledge page"
                    ),
                    path=page.path,
                    metadata={"kind": page.kind},
                )
            )

    if search_index is not None:
        indexed = {page.path for page in search_index.pages}
        for page in pages:
            if page.path not in indexed:
                issues.append(
                    LintIssue(
                        rule=RULE_UNINDEXED_PAGE,
                        severity=RULE_SEVERITIES[RULE_UNINDEXED_PAGE],
                        message=f"{page.path}: page is missing from the search index",
                        path=page.path,
                        metadata={"kind": page.kind},
                    )
                )
    return issues


def lint_sources(
    knowledge_base: KnowledgeBase,
    *,
    page_paths: Optional[Dict[str, str]] = None,
) -> List[LintIssue]:
    """Knowledge without any source reference."""

    paths = page_paths or {}
    issues: List[LintIssue] = []
    for kind, label, items in (
        ("entity", _entity_label, knowledge_base.entities),
        ("concept", _entity_label, knowledge_base.concepts),
        ("fact", _fact_label, knowledge_base.facts),
        ("relation", _relation_label, knowledge_base.relations),
    ):
        for item in items:
            if item.sources:
                continue
            name = label(item)
            issues.append(
                LintIssue(
                    rule=RULE_MISSING_SOURCE,
                    severity=RULE_SEVERITIES[RULE_MISSING_SOURCE],
                    message=f"{kind} {_short(name)!r} has no source reference",
                    path=paths.get(item.id, ""),
                    object_id=item.id,
                    metadata={"kind": kind, "name": name},
                )
            )
    return issues


def lint_knowledge(
    *,
    graph: Optional[Graph] = None,
    link_result: Optional[Any] = None,
    page_paths: Optional[Dict[str, str]] = None,
) -> List[LintIssue]:
    """Unlinked facts/relations (from the graph) and ambiguous names."""

    paths = page_paths or {}
    issues: List[LintIssue] = []

    if graph is not None:
        node_keys = {
            key for node in graph.get_nodes() for key in node.name_keys()
        }
        for fact in graph.unlinked_facts:
            complete = bool(fact.subject and fact.predicate and fact.object)
            reason = (
                "endpoint not found in graph"
                if complete
                else "incomplete triple (subject/predicate/object)"
            )
            issues.append(
                LintIssue(
                    rule=RULE_UNLINKED_FACT,
                    severity=RULE_SEVERITIES[RULE_UNLINKED_FACT],
                    message=(
                        f"fact {_short(fact.statement)!r} is not linked in the "
                        f"graph: {reason}"
                    ),
                    path=paths.get(fact.id, ""),
                    object_id=fact.id,
                    metadata={
                        "statement": fact.statement,
                        "subject": fact.subject,
                        "predicate": fact.predicate,
                        "object": fact.object,
                        "reason": reason,
                    },
                )
            )
        for relation in graph.unlinked_relations:
            missing = [
                name
                for name in (relation.source, relation.target)
                if match_key(name) not in node_keys
            ]
            reason = (
                "endpoint not found in graph" if missing else "endpoint ambiguous"
            )
            issues.append(
                LintIssue(
                    rule=RULE_UNLINKED_RELATION,
                    severity=RULE_SEVERITIES[RULE_UNLINKED_RELATION],
                    message=(
                        f"relation {_short(relation.source)!r} -> "
                        f"{_short(relation.target)!r} is not linked in the graph: "
                        f"{reason}"
                    ),
                    object_id=relation.id,
                    metadata={
                        "source": relation.source,
                        "target": relation.target,
                        "type": relation.type,
                        "reason": reason,
                    },
                )
            )

    reported: Dict[str, List[str]] = {}
    if graph is not None:
        for name in graph.metadata.get("ambiguous_names", []):
            reported.setdefault(name, []).append("graph")
    if link_result is not None:
        for name in link_result.metadata.get("ambiguous_names", []):
            reported.setdefault(name, []).append("link_result")
    for name in sorted(reported):
        issues.append(
            LintIssue(
                rule=RULE_AMBIGUOUS_NAME,
                severity=RULE_SEVERITIES[RULE_AMBIGUOUS_NAME],
                message=f"name {name!r} matches more than one object",
                metadata={
                    "name": name,
                    "reported_by": sorted(set(reported[name])),
                },
            )
        )
    return issues


def lint_graph(
    graph: Graph, *, page_paths: Optional[Dict[str, str]] = None
) -> List[LintIssue]:
    """Dangling edges, isolated nodes and (allowed) self loops."""

    paths = page_paths or {}
    issues: List[LintIssue] = []
    nodes = graph.get_nodes()
    by_id = {node.id: node for node in nodes}
    by_key: Dict[str, List[str]] = {}
    for node in nodes:
        for key in node.name_keys():
            by_key.setdefault(key, []).append(node.id)

    def unknown(name: str, pinned: Optional[str]) -> bool:
        if pinned:
            return pinned not in by_id
        return match_key(name) not in by_key

    for edge in graph.get_edges():
        dangling = []
        if unknown(edge.source, edge.source_id):
            dangling.append("source")
        if unknown(edge.target, edge.target_id):
            dangling.append("target")
        if dangling:
            issues.append(
                LintIssue(
                    rule=RULE_DANGLING_EDGE,
                    severity=RULE_SEVERITIES[RULE_DANGLING_EDGE],
                    message=(
                        f"edge {edge.source!r} --{edge.type}--> "
                        f"{edge.target!r} has an unknown "
                        f"{' and '.join(dangling)} endpoint"
                    ),
                    object_id=edge.source_id or "",
                    metadata={
                        "source": edge.source,
                        "target": edge.target,
                        "type": edge.type,
                        "endpoints": dangling,
                    },
                )
            )
        if edge.is_self_loop:
            issues.append(
                LintIssue(
                    rule=RULE_SELF_LOOP,
                    severity=RULE_SEVERITIES[RULE_SELF_LOOP],
                    message=(
                        f"self loop {edge.source!r} --{edge.type}--> "
                        f"{edge.target!r} is allowed"
                    ),
                    object_id=edge.source_id or "",
                    metadata={"source": edge.source, "type": edge.type},
                )
            )

    for node in nodes:
        if graph.incoming(node.id) or graph.outgoing(node.id):
            continue
        issues.append(
            LintIssue(
                rule=RULE_ISOLATED_NODE,
                severity=RULE_SEVERITIES[RULE_ISOLATED_NODE],
                message=f"{node.kind} {_short(node.title)!r} has no edges",
                path=paths.get(node.id, ""),
                object_id=node.id,
                metadata={"kind": node.kind, "title": node.title},
            )
        )
    return issues


def _is_external(target: str) -> bool:
    """Links the linter should not try to resolve to a wiki file."""

    if not target:
        return True
    return (
        "://" in target
        or target.startswith(("#", "/", "mailto:", "tel:"))
    )


def _resolve(page_path: str, target: str) -> str:
    directory = posixpath.dirname(page_path.replace("\\", "/"))
    joined = posixpath.join(directory, target) if directory else target
    return posixpath.normpath(joined).replace("\\", "/")


def _is_index(page: PageText, index_name: str) -> bool:
    if page.kind == "index":
        return True
    return Path(page.path).stem.casefold() == index_name.casefold()


def _entity_label(item: Any) -> str:
    return item.name


def _fact_label(item: Any) -> str:
    return item.statement


def _relation_label(item: Any) -> str:
    return f"{item.source} -> {item.target}"


def _short(text: str, limit: int = MAX_LABEL_CHARS) -> str:
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"
