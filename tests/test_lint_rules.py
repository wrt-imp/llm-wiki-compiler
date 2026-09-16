"""Rule tests: one check at a time."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from compiler.graph import Edge, Graph, Node, build_graph
from compiler.lint import (
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
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    PageText,
    lint_graph,
    lint_knowledge,
    lint_links,
    lint_pages,
    lint_sources,
)
from support import (
    concept,
    entity,
    fact,
    make_kb,
    relation,
    src_ref,
    write_wiki_page,
)


# ----------------------------------------------------------------------
# lint_links
# ----------------------------------------------------------------------
def test_dead_link_is_reported(tmp_path: Path) -> None:
    issues = lint_links([PageText("a.md", "[x](missing.md)\n")], root=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule == RULE_DEAD_LINK
    assert issues[0].severity == SEVERITY_ERROR
    assert issues[0].path == "a.md"
    assert issues[0].metadata["target"] == "missing.md"


def test_existing_link_is_not_reported(tmp_path: Path) -> None:
    write_wiki_page(tmp_path, "b.md", "# B\n")
    pages = [PageText("a.md", "[x](b.md)\n"), PageText("b.md", "# B\n")]

    assert lint_links(pages, root=tmp_path) == []


def test_external_and_anchor_links_are_ignored(tmp_path: Path) -> None:
    text = "[a](https://example.com) [b](#section) [c](mailto:x@y) [d]()\n"

    assert lint_links([PageText("a.md", text)], root=tmp_path) == []


def test_link_is_resolved_relative_to_the_page(tmp_path: Path) -> None:
    write_wiki_page(tmp_path, "b.md", "# B\n")
    pages = [PageText("sub/a.md", "[x](../b.md)\n"), PageText("b.md", "# B\n")]

    assert lint_links(pages, root=tmp_path) == []


# ----------------------------------------------------------------------
# lint_pages
# ----------------------------------------------------------------------
def test_page_only_linked_from_the_index_is_an_orphan() -> None:
    pages = [
        PageText("index.md", "- [A](a.md)\n- [B](b.md)\n", kind="index"),
        PageText("a.md", "# A\n"),
        PageText("b.md", "[A](a.md)\n"),
    ]

    issues = lint_pages(pages)

    assert [issue.path for issue in issues] == ["b.md"]
    assert issues[0].rule == RULE_ORPHAN_PAGE
    assert issues[0].severity == SEVERITY_WARNING


def test_linked_page_is_not_an_orphan() -> None:
    pages = [
        PageText("index.md", "- [A](a.md)\n", kind="index"),
        PageText("a.md", "[B](b.md)\n"),
        PageText("b.md", "[A](a.md)\n"),
    ]

    assert lint_pages(pages) == []


def test_index_page_is_never_reported() -> None:
    pages = [PageText("index.md", "# Knowledge Wiki\n", kind="index")]

    assert lint_pages(pages) == []


def test_pages_missing_from_the_search_index_are_reported() -> None:
    pages = [PageText("a.md", "# A\n"), PageText("b.md", "# B\n")]
    search_index = SimpleNamespace(pages=[SimpleNamespace(path="a.md")])

    issues = [
        issue
        for issue in lint_pages(pages, search_index=search_index)
        if issue.rule == RULE_UNINDEXED_PAGE
    ]

    assert len(issues) == 1
    assert issues[0].path == "b.md"


# ----------------------------------------------------------------------
# lint_sources
# ----------------------------------------------------------------------
def test_every_kind_without_sources_is_reported() -> None:
    kb = make_kb(
        entities=(entity("解析器"),),
        concepts=(concept("文档模型"),),
        facts=(fact("解析器输出文档模型"),),
        relations=(relation("解析器", "文档模型", type="produces"),),
    )

    issues = lint_sources(kb)

    assert [issue.metadata["kind"] for issue in issues] == [
        "entity",
        "concept",
        "fact",
        "relation",
    ]
    assert all(issue.rule == RULE_MISSING_SOURCE for issue in issues)
    assert all(issue.severity == SEVERITY_WARNING for issue in issues)
    assert all(issue.object_id for issue in issues)


def test_items_with_sources_are_not_reported() -> None:
    kb = make_kb(
        entities=(entity("解析器", sources=(src_ref("docA"),)),),
        concepts=(concept("文档模型", sources=(src_ref("docA"),)),),
        facts=(fact("解析器输出文档模型", sources=(src_ref("docA"),)),),
        relations=(
            relation("解析器", "文档模型", type="produces", sources=(src_ref("docA"),)),
        ),
    )

    assert lint_sources(kb) == []


def test_page_paths_are_used_when_known() -> None:
    item = entity("解析器")
    kb = make_kb(entities=(item,))

    issues = lint_sources(kb, page_paths={item.id: "解析器.md"})

    assert issues[0].path == "解析器.md"


# ----------------------------------------------------------------------
# lint_knowledge
# ----------------------------------------------------------------------
def test_unlinked_facts_report_their_reason() -> None:
    kb = make_kb(
        entities=(entity("解析器"), entity("文档模型")),
        facts=(
            fact("解析器很重要", subject="解析器"),
            fact("解析器使用幽灵", subject="解析器", predicate="使用", object="幽灵"),
        ),
    )
    graph = build_graph(kb)

    issues = lint_knowledge(graph=graph)

    assert [issue.rule for issue in issues] == [RULE_UNLINKED_FACT] * 2
    reasons = {issue.metadata["reason"] for issue in issues}
    assert reasons == {
        "incomplete triple (subject/predicate/object)",
        "endpoint not found in graph",
    }


def test_unlinked_relations_report_their_reason() -> None:
    kb = make_kb(
        entities=(entity("解析器"),),
        relations=(relation("解析器", "幽灵", type="uses"),),
    )
    graph = build_graph(kb)

    issues = lint_knowledge(graph=graph)

    assert len(issues) == 1
    assert issues[0].rule == RULE_UNLINKED_RELATION
    assert issues[0].metadata["reason"] == "endpoint not found in graph"


def test_ambiguous_names_merge_both_reports() -> None:
    kb = make_kb(
        entities=(entity("Python"), entity("解析器")),
        concepts=(concept("python"),),
        relations=(relation("Python", "解析器", type="uses"),),
    )
    graph = build_graph(kb)
    link_result = SimpleNamespace(metadata={"ambiguous_names": ["python"]})

    issues = [i for i in lint_knowledge(graph=graph, link_result=link_result) if i.rule == RULE_AMBIGUOUS_NAME]

    assert len(issues) == 1
    assert issues[0].metadata["name"] == "python"
    assert issues[0].metadata["reported_by"] == ["graph", "link_result"]
    assert issues[0].severity == SEVERITY_WARNING


def test_ambiguous_names_from_the_link_result_alone() -> None:
    link_result = SimpleNamespace(metadata={"ambiguous_names": ["python"]})

    issues = lint_knowledge(link_result=link_result)

    assert [issue.rule for issue in issues] == [RULE_AMBIGUOUS_NAME]


# ----------------------------------------------------------------------
# lint_graph
# ----------------------------------------------------------------------
def test_dangling_edge_with_unknown_pinned_id() -> None:
    graph = Graph(
        nodes=[Node(id="e1", kind="entity", title="解析器")],
        edges=[
            Edge(
                source="解析器",
                target="文档模型",
                type="uses",
                kind="relation",
                metadata={"source_id": "ghost", "target_id": None},
            )
        ],
    )

    issues = [i for i in lint_graph(graph) if i.rule == RULE_DANGLING_EDGE]

    assert len(issues) == 1
    assert issues[0].severity == SEVERITY_ERROR
    assert issues[0].metadata["endpoints"] == ["source", "target"]


def test_dangling_edge_with_unknown_name() -> None:
    graph = Graph(
        nodes=[Node(id="e1", kind="entity", title="解析器")],
        edges=[
            Edge(source="解析器", target="幽灵", type="uses", kind="relation")
        ],
    )

    issues = [i for i in lint_graph(graph) if i.rule == RULE_DANGLING_EDGE]

    assert len(issues) == 1
    assert issues[0].metadata["endpoints"] == ["target"]


def test_isolated_node_is_a_warning() -> None:
    graph = Graph(nodes=[Node(id="e1", kind="entity", title="孤岛")])

    issues = lint_graph(graph)

    assert [issue.rule for issue in issues] == [RULE_ISOLATED_NODE]
    assert issues[0].severity == SEVERITY_WARNING
    assert issues[0].object_id == "e1"


def test_self_loop_is_info_not_error() -> None:
    graph = Graph(
        nodes=[Node(id="e1", kind="entity", title="解析器")],
        edges=[
            Edge(
                source="解析器",
                target="解析器",
                type="depends on",
                kind="relation",
                metadata={"source_id": "e1", "target_id": "e1"},
            )
        ],
    )

    issues = lint_graph(graph)

    assert [issue.rule for issue in issues] == [RULE_SELF_LOOP]
    assert issues[0].severity == SEVERITY_INFO


def test_healthy_graph_has_no_issues() -> None:
    graph = Graph(
        nodes=[
            Node(id="e1", kind="entity", title="解析器"),
            Node(id="c1", kind="concept", title="文档模型"),
        ],
        edges=[
            Edge(
                source="解析器",
                target="文档模型",
                type="produces",
                kind="relation",
                metadata={"source_id": "e1", "target_id": "c1"},
            )
        ],
    )

    assert lint_graph(graph) == []
