"""Front matter parsing tests."""

from __future__ import annotations

from compiler.search import as_list, parse_front_matter

GENERATED = (
    "---\n"
    'id: "a7755ec09b9f5bed"\n'
    'kind: "entity"\n'
    'type: "system"\n'
    "aliases:\n"
    '  - "Parser"\n'
    'page: "解析器.md"\n'
    "---\n"
    "# 解析器\n"
    "\n"
    "正文\n"
)


def test_parses_the_generated_front_matter() -> None:
    front = parse_front_matter(GENERATED)

    assert front.present is True
    assert front.data == {
        "id": "a7755ec09b9f5bed",
        "kind": "entity",
        "type": "system",
        "aliases": ["Parser"],
        "page": "解析器.md",
    }
    assert front.warning == ""


def test_body_starts_after_the_front_matter() -> None:
    front = parse_front_matter(GENERATED)

    assert front.body.startswith("# 解析器\n")
    assert "kind:" not in front.body
    assert "a7755ec09b9f5bed" not in front.body


def test_file_without_front_matter() -> None:
    front = parse_front_matter("# Knowledge Wiki\n\nbody\n")

    assert front.present is False
    assert front.data == {}
    assert front.body.startswith("# Knowledge Wiki")


def test_unterminated_front_matter_is_reported_not_fatal() -> None:
    text = '---\nid: "abc"\n# 标题\n'

    front = parse_front_matter(text)

    assert front.present is False
    assert front.body == text
    assert "no closing" in front.warning


def test_unquoted_values_are_read() -> None:
    front = parse_front_matter("---\nid: abc123\nkind: concept\n---\nbody\n")

    assert front.data == {"id": "abc123", "kind": "concept"}


def test_comments_and_blank_lines_are_ignored() -> None:
    text = '---\n# a comment\n\nid: "abc"\n\n\nkind: "entity"\n---\nbody\n'

    assert parse_front_matter(text).data == {"id": "abc", "kind": "entity"}


def test_escapes_are_undone() -> None:
    text = '---\nid: "a\\"b\\\\c"\n---\nbody\n'

    assert parse_front_matter(text).data["id"] == 'a"b\\c'


def test_multiple_aliases() -> None:
    text = "---\naliases:\n  - \"Parser\"\n  - \"解析器 core\"\n---\nbody\n"

    assert parse_front_matter(text).data["aliases"] == ["Parser", "解析器 core"]


def test_as_list_coerces_values() -> None:
    assert as_list(None) == []
    assert as_list("") == []
    assert as_list("Parser") == ["Parser"]
    assert as_list(["a", " b "]) == ["a", "b"]
    assert as_list(42) == ["42"]
