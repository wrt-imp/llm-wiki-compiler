"""Deterministic normalization tests (no LLM anywhere)."""

from __future__ import annotations

from compiler.merge import (
    alias_keys,
    compact_key,
    match_key,
    similarity,
    statement_key,
    tokens,
)


def test_match_key_ignores_case_and_spacing() -> None:
    assert match_key("Parser") == "parser"
    assert match_key("  parser  ") == "parser"
    assert match_key("Document   Model") == "document model"


def test_match_key_normalizes_width_and_wrapping() -> None:
    assert match_key("\uff30\uff41\uff52\uff53\uff45\uff52") == "parser"  # full width
    assert match_key('"Parser"') == "parser"
    assert match_key("\u300a\u6587\u6863\u6a21\u578b\u300b") == "\u6587\u6863\u6a21\u578b"
    assert match_key("(Parser)") == "parser"


def test_match_key_strips_edge_punctuation() -> None:
    assert match_key("\u89e3\u6790\u5668\u3002") == "\u89e3\u6790\u5668"
    assert match_key("-- parser --") == "parser"
    assert match_key("") == ""
    assert match_key("   ") == ""


def test_compact_key_removes_whitespace() -> None:
    assert compact_key("Document Model") == "documentmodel"
    assert compact_key("\u6587\u6863 \u6a21\u578b") == "\u6587\u6863\u6a21\u578b"


def test_statement_key_ignores_case_and_final_stop() -> None:
    assert statement_key("Parser outputs Document.") == statement_key(
        "parser outputs document"
    )
    assert statement_key("\u89e3\u6790\u5668\u8f93\u51fa Document\u3002") == (
        "\u89e3\u6790\u5668\u8f93\u51fa document"
    )


def test_alias_keys_are_ordered_and_unique() -> None:
    keys = alias_keys("Parser", ["parser", "  PARSER ", "\u89e3\u6790\u5668", ""])

    assert keys == ["parser", "\u89e3\u6790\u5668"]


def test_tokens_only_use_ascii_words() -> None:
    assert tokens("Knowledge Graph 2.0") == {"knowledge", "graph"}
    assert tokens("\u77e5\u8bc6\u56fe\u8c31") == frozenset()


def test_similarity() -> None:
    assert similarity("parser", "parser") == 1.0
    assert similarity("parser", "parsers") > 0.85
    assert similarity("parser", "\u6587\u6863\u6a21\u578b") < 0.5
