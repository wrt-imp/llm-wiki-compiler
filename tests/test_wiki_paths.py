"""Wiki page file naming tests."""

from __future__ import annotations

from compiler.wiki import (
    MAX_STEM_LENGTH,
    PageTarget,
    assign_page_paths,
    page_filename,
    safe_stem,
)


def target(title: str, kind: str = "entity", object_id: str = "id1") -> PageTarget:
    return PageTarget(kind=kind, object_id=object_id, title=title)


def test_safe_stem_keeps_chinese_titles() -> None:
    assert safe_stem("编程语言") == "编程语言"
    assert safe_stem(" 面向对象编程 ") == "面向对象编程"


def test_safe_stem_replaces_illegal_characters() -> None:
    assert safe_stem("Python/编程:语言") == "Python-编程-语言"
    assert safe_stem('a*b?c"d<e>f|g') == "a-b-c-d-e-f-g"
    assert safe_stem("back\\slash") == "back-slash"


def test_safe_stem_drops_trailing_dots_and_spaces() -> None:
    assert safe_stem("name . ") == "name"
    assert safe_stem(".hidden") == "hidden"


def test_safe_stem_falls_back_when_nothing_is_left() -> None:
    assert safe_stem("   ") == "page"
    assert safe_stem("///") == "page"
    assert safe_stem("") == "page"


def test_safe_stem_escapes_windows_device_names() -> None:
    assert safe_stem("CON") == "_CON"
    assert safe_stem("com1") == "_com1"
    assert safe_stem("LPT9") == "_LPT9"
    assert safe_stem("console") == "console"


def test_safe_stem_truncates_long_names_with_the_object_id() -> None:
    stem = safe_stem("很长的名字" * 40, object_id="abcd1234")

    assert len(stem) <= MAX_STEM_LENGTH
    assert stem.endswith("-abcd1234")


def test_page_filename_uses_the_object_name() -> None:
    assert page_filename("Python", kind="entity", object_id="x") == "Python.md"
    assert (
        page_filename("编程语言", kind="concept", object_id="x", extension=".markdown")
        == "编程语言.markdown"
    )


def test_assign_page_paths_for_a_single_target() -> None:
    pages = assign_page_paths([target("解析器")])

    assert [page.path for page in pages] == ["解析器.md"]
    assert pages[0].kind == "entity"
    assert pages[0].object_id == "id1"
    assert pages[0].title == "解析器"


def test_assign_page_paths_keeps_aliases() -> None:
    pages = assign_page_paths(
        [PageTarget(kind="entity", object_id="x", title="解析器", aliases=("Parser",))]
    )

    assert pages[0].aliases == ("Parser",)


def test_assign_page_paths_resolves_entity_concept_collision() -> None:
    pages = assign_page_paths(
        [
            target("Python", kind="entity", object_id="entityid"),
            target("python", kind="concept", object_id="conceptid"),
        ]
    )

    assert [page.path for page in pages] == ["Python-entity.md", "python-concept.md"]


def test_assign_page_paths_is_case_insensitive() -> None:
    pages = assign_page_paths(
        [
            target("Python", object_id="aaaa1111"),
            target("python", object_id="bbbb2222"),
        ]
    )

    paths = [page.path for page in pages]
    assert len(set(path.lower() for path in paths)) == 2
    assert paths[0] == "Python-entity.md"
    assert paths[1].startswith("python-entity-bbbb2222")


def test_assign_page_paths_avoids_reserved_names() -> None:
    pages = assign_page_paths([target("index", object_id="abc12345")], reserved={"index"})

    assert pages[0].path == "index-abc12345.md"


def test_assign_page_paths_is_deterministic() -> None:
    targets = [
        target("Python", kind="entity", object_id="e1"),
        target("python", kind="concept", object_id="c1"),
        target("解析器", object_id="e2"),
    ]

    first = assign_page_paths(targets)
    second = assign_page_paths(targets)

    assert [page.path for page in first] == [page.path for page in second]
