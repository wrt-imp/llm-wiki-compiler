"""The lint() entry point: aggregation, stability and read only behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler.graph import build_graph
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
    LintResult,
    lint,
)
from compiler.search import index_wiki
from support import (
    clean_wiki,
    concept,
    entity,
    fact,
    make_kb,
    relation,
    src_ref,
    wiki_kb,
    write_wiki_page,
)


def broken_kb():
    return make_kb(
        entities=(
            entity("解析器", aliases=("Parser",), sources=(src_ref("docA", quote="q1"),)),
            entity("孤立实体"),
        ),
        concepts=(concept("python"),),
        facts=(fact("解析器很重要", subject="解析器"),),
        relations=(
            relation(
                "解析器",
                "解析器",
                type="depends on",
                sources=(src_ref("docA", quote="q2"),),
            ),
            relation("解析器", "幽灵", type="uses"),
        ),
    )


def test_clean_wiki_has_no_issues(tmp_path: Path) -> None:
    kb, build, links = clean_wiki(tmp_path)

    result = lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))

    assert result.issues == []
    assert result.is_clean() is True
    assert result.counts["errors"] == 0
    assert result.counts["warnings"] == 0
    assert result.metadata["pages_checked"] == 4


def test_empty_wiki_and_knowledge_base(tmp_path: Path) -> None:
    from compiler.wiki import generate_wiki

    kb = make_kb()
    build = generate_wiki(kb, tmp_path / "wiki")

    result = lint(kb, wiki_build=build)

    assert result.is_clean() is True
    assert result.metadata["pages_checked"] == 1


def test_no_inputs_is_an_error() -> None:
    with pytest.raises(ValueError):
        lint()


def test_knowledge_base_only_skips_the_other_rules(tmp_path: Path) -> None:
    kb = make_kb(entities=(entity("解析器"),))

    result = lint(kb)

    assert [issue.rule for issue in result.issues] == [RULE_MISSING_SOURCE]
    assert result.metadata["rules_run"] == [RULE_MISSING_SOURCE]
    for rule in (RULE_DEAD_LINK, RULE_ORPHAN_PAGE, RULE_DANGLING_EDGE, RULE_SELF_LOOP):
        assert rule in result.metadata["skipped_rules"]


def test_link_result_only_runs_the_page_rules(tmp_path: Path) -> None:
    kb = wiki_kb()
    from compiler.wiki import generate_wiki

    build = generate_wiki(kb, tmp_path / "wiki")
    links = __import__("compiler.linker", fromlist=["resolve_wiki"]).resolve_wiki(build)

    result = lint(link_result=links)

    assert RULE_DEAD_LINK in result.metadata["rules_run"]
    assert RULE_ORPHAN_PAGE in result.metadata["rules_run"]
    assert RULE_MISSING_SOURCE in result.metadata["skipped_rules"]
    assert result.metadata["pages_checked"] == len(links.files)


def test_broken_wiki_reports_every_category(tmp_path: Path) -> None:
    from compiler.linker import resolve_wiki
    from compiler.wiki import generate_wiki

    kb = broken_kb()
    build = generate_wiki(kb, tmp_path / "wiki")
    links = resolve_wiki(build)

    result = lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))
    counts = result.counts

    assert counts["errors"] == 0
    assert counts["missing_sources"] == 4
    # 解析器, 孤立实体 and the python concept page are only reachable via index.md
    assert counts["orphan_pages"] == 3
    assert counts["unlinked_facts"] == 1
    assert counts["unlinked_relations"] == 1
    assert counts["isolated_node"] == 2
    assert counts["self_loops"] == 1
    assert counts["infos"] == 1
    assert counts["dead_links"] == 0


def test_dead_link_is_an_error(tmp_path: Path) -> None:
    from compiler.wiki import generate_wiki

    kb = make_kb(entities=(entity("解析器", sources=(src_ref("docA"),)),))
    build = generate_wiki(kb, tmp_path / "wiki")
    write_wiki_page(
        tmp_path / "wiki", "解析器.md", "# 解析器\n\n[幽灵](幽灵.md)\n"
    )

    result = lint(kb, wiki_build=build)

    assert result.counts["errors"] == 1
    assert result.by_rule(RULE_DEAD_LINK)[0].severity == SEVERITY_ERROR
    assert result.by_rule(RULE_DEAD_LINK)[0].metadata["target"] == "幽灵.md"


def test_severities_match_the_specification(tmp_path: Path) -> None:
    from compiler.linker import resolve_wiki
    from compiler.wiki import generate_wiki

    kb = broken_kb()
    build = generate_wiki(kb, tmp_path / "wiki")
    links = resolve_wiki(build)
    result = lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))

    severities = {issue.rule: issue.severity for issue in result.issues}
    assert severities[RULE_MISSING_SOURCE] == SEVERITY_WARNING
    assert severities[RULE_ORPHAN_PAGE] == SEVERITY_WARNING
    assert severities[RULE_UNLINKED_FACT] == SEVERITY_WARNING
    assert severities[RULE_UNLINKED_RELATION] == SEVERITY_WARNING
    assert severities[RULE_ISOLATED_NODE] == SEVERITY_WARNING
    assert severities[RULE_SELF_LOOP] == SEVERITY_INFO


def test_issues_are_sorted_by_severity_then_rule(tmp_path: Path) -> None:
    from compiler.linker import resolve_wiki
    from compiler.wiki import generate_wiki

    kb = broken_kb()
    build = generate_wiki(kb, tmp_path / "wiki")
    links = resolve_wiki(build)
    result = lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))

    keys = [issue.sort_key for issue in result.issues]

    assert keys == sorted(keys)
    assert result.issues[-1].severity == SEVERITY_INFO


def test_two_runs_are_identical(tmp_path: Path) -> None:
    kb, build, links = clean_wiki(tmp_path)
    first = lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))
    second = lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))

    assert json.dumps(first.to_dict(), ensure_ascii=False) == json.dumps(
        second.to_dict(), ensure_ascii=False
    )


def test_result_round_trip_after_a_real_run(tmp_path: Path) -> None:
    from compiler.linker import resolve_wiki
    from compiler.wiki import generate_wiki

    kb = broken_kb()
    build = generate_wiki(kb, tmp_path / "wiki")
    result = lint(kb, wiki_build=build, link_result=resolve_wiki(build), graph=build_graph(kb))

    restored = LintResult.from_dict(json.loads(json.dumps(result.to_dict(), ensure_ascii=False)))

    assert restored == result


def test_unindexed_pages_are_reported(tmp_path: Path) -> None:
    kb, build, links = clean_wiki(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    result = lint(
        kb, wiki_build=build, search_index=index_wiki(empty)
    )

    assert result.counts["unindexed_pages"] == len(links.files)
    assert RULE_UNINDEXED_PAGE in result.metadata["rules_run"]


def test_indexed_pages_are_not_reported(tmp_path: Path) -> None:
    kb, build, _ = clean_wiki(tmp_path)
    search_index = index_wiki(tmp_path / "wiki")

    result = lint(kb, wiki_build=build, search_index=search_index)

    assert result.by_rule(RULE_UNINDEXED_PAGE) == []


def test_lint_does_not_modify_the_knowledge_base(tmp_path: Path) -> None:
    kb, build, links = clean_wiki(tmp_path)
    before = kb.to_dict()

    lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))

    assert kb.to_dict() == before


def test_lint_does_not_modify_the_wiki_files(tmp_path: Path) -> None:
    kb, build, links = clean_wiki(tmp_path)
    wiki = tmp_path / "wiki"
    before = {path.name: path.read_bytes() for path in wiki.iterdir()}

    lint(kb, wiki_build=build, link_result=links, graph=build_graph(kb))

    after = {path.name: path.read_bytes() for path in wiki.iterdir()}
    assert before == after


def test_lint_does_not_modify_the_graph_or_link_result(tmp_path: Path) -> None:
    kb, build, links = clean_wiki(tmp_path)
    graph = build_graph(kb)
    graph_before = graph.to_dict()
    links_before = (dict(links.counts), dict(links.metadata), list(links.files))

    lint(kb, wiki_build=build, link_result=links, graph=graph)

    assert graph.to_dict() == graph_before
    assert (dict(links.counts), dict(links.metadata), list(links.files)) == links_before
