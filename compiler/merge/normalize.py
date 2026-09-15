"""Deterministic normalization for names and statements.

Pure code, no LLM: this is what makes "Parser", " parser " and "Ｐａｒｓｅｒ"
the same key before anything semantic happens.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Sequence

#: Pairs of characters that may wrap a name inside running text.
_WRAP_PAIRS = {
    "'": "'",
    '"': '"',
    "`": "`",
    "\u201c": "\u201d",
    "\u2018": "\u2019",
    "\u300c": "\u300d",
    "\u300e": "\u300f",
    "\u300a": "\u300b",
    "\u3008": "\u3009",
    "(": ")",
    "[": "]",
    "{": "}",
    "\u3010": "\u3011",
    "\uff08": "\uff09",
    "\uff3b": "\uff3d",
    "\uff5b": "\uff5d",
}

#: Punctuation that carries no meaning at the edges of a name.
_EDGE_PUNCTUATION = (
    "\u3002\uff0c\u3001\uff0e,.;:!?\uff01\uff1f\u2026\u2014-\u2013~\u00b7"
    "\"'\u201c\u201d\u2018\u2019()[]{}\uff08\uff09\u3010\u3011\u300a\u300b\u3008\u3009"
    "\u300c\u300d\u300e\u300f"
)

_EDGE_RE = re.compile(
    "^[{0}]+|[{0}]+$".format(re.escape(_EDGE_PUNCTUATION))
)
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[0-9a-z]+")


def match_key(name: str) -> str:
    """Return the key that decides two names are literally the same.

    Normalizes unicode width (NFKC), case, surrounding quotes/brackets,
    leading and trailing punctuation, and repeated whitespace.
    """

    text = unicodedata.normalize("NFKC", str(name or "")).strip()
    text = _strip_wrapping(text)
    text = _WHITESPACE_RE.sub(" ", text.casefold()).strip()
    text = _EDGE_RE.sub("", text).strip()
    text = _strip_wrapping(text)
    return _EDGE_RE.sub("", text).strip()


def compact_key(name: str) -> str:
    """``match_key`` without any whitespace: "文档 模型" -> "文档模型"."""

    return _WHITESPACE_RE.sub("", match_key(name))


def statement_key(statement: str) -> str:
    """Key for duplicate fact detection (case, spacing and final stop)."""

    return match_key(statement).rstrip("\u3002.!?\uff01\uff1f\u2026").strip()


def alias_keys(name: str, aliases: Sequence[str] = ()) -> List[str]:
    """Ordered, de-duplicated match keys of a name and its aliases."""

    keys: List[str] = []
    for candidate in [name, *aliases]:
        key = match_key(candidate)
        if key and key not in keys:
            keys.append(key)
    return keys


def tokens(name: str) -> frozenset:
    """Lower case word tokens of a name (for the token overlap rule).

    Only ASCII words/digits become tokens, so CJK names simply have none and
    the token rule stays out of the way for them.
    """

    return frozenset(
        token for token in _TOKEN_RE.findall(match_key(name)) if len(token) > 1
    )


def similarity(left: str, right: str) -> float:
    """Character level similarity of two names (0.0 - 1.0)."""

    return SequenceMatcher(None, compact_key(left), compact_key(right)).ratio()


def _strip_wrapping(text: str) -> str:
    """Drop wrapping quotes/brackets, repeatedly: ``("Parser")`` -> ``Parser``."""

    while len(text) >= 2:
        closing = _WRAP_PAIRS.get(text[0])
        if closing is None or text[-1] != closing:
            break
        text = text[1:-1].strip()
    return text
