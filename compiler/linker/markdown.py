"""Markdown aware scanning: which characters must not be linked.

The resolver never rewrites a page blindly. This module marks the spans that
belong to markdown structure or to existing links, so the name matcher only
ever sees prose:

* YAML front matter
* fenced code blocks (``` / ~~~), including the fence lines
* heading lines (``# 标题``)
* inline code (`code`)
* existing links: ``[[wiki]]``, ``[text](target)``, ``[text][ref]``
* autolinks / html tags (``<...>``)
* reference definitions (``[ref]: target``)
* optionally the whole ``## Sources`` section
"""

from __future__ import annotations

import re
from typing import Iterator, List, Sequence, Tuple

Span = Tuple[int, int]

_FRONT_MATTER_DELIMITER = "---"
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_HEADING_RE = re.compile(r"^#{1,6}\s")
_REFERENCE_DEFINITION_RE = re.compile(r"^\[[^\]]+\]:\s*\S+")

_INLINE_PATTERNS: Sequence[re.Pattern] = (
    re.compile(r"(?P<ticks>`+)(?P<body>.+?)(?P=ticks)"),
    re.compile(r"\[\[[^\]]*\]\]"),
    re.compile(r"\[[^\]]*\]\([^)]*\)"),
    re.compile(r"\[[^\]]*\]\[[^\]]*\]"),
    re.compile(r"<[^>\n]*>"),
)


def protected_spans(
    text: str,
    *,
    skip_sources_section: bool = True,
    sources_heading: str = "Sources",
) -> List[Span]:
    """Return the spans of ``text`` that must stay untouched."""

    spans: List[Span] = []
    in_fence = False
    in_sources = False
    front_matter_end = _front_matter_end(text)

    for start, end, line in _iter_lines(text):
        if front_matter_end and end <= front_matter_end:
            spans.append((start, end))
            continue

        if _FENCE_RE.match(line):
            in_fence = not in_fence
            spans.append((start, end))
            continue
        if in_fence:
            spans.append((start, end))
            continue

        if _HEADING_RE.match(line):
            spans.append((start, end))
            if skip_sources_section:
                if in_sources:
                    in_sources = False
                elif _is_sources_heading(line, sources_heading):
                    in_sources = True
            continue
        if in_sources:
            spans.append((start, end))
            continue

        if _REFERENCE_DEFINITION_RE.match(line):
            spans.append((start, end))
            continue

        spans.extend(_inline_spans(start, line))

    return _merge(spans)


def _is_sources_heading(line: str, sources_heading: str) -> bool:
    text = line.strip().lstrip("#").strip()
    return text.casefold() == sources_heading.casefold()


def _inline_spans(line_start: int, line: str) -> List[Span]:
    spans: List[Span] = []
    for pattern in _INLINE_PATTERNS:
        for match in pattern.finditer(line):
            spans.append((line_start + match.start(), line_start + match.end()))
    return spans


def _front_matter_end(text: str) -> int:
    """Offset just after the closing ``---`` of the front matter (0 = none)."""

    lines = list(_iter_lines(text))
    if not lines or lines[0][2].strip() != _FRONT_MATTER_DELIMITER:
        return 0
    for _, end, line in lines[1:]:
        if line.strip() in (_FRONT_MATTER_DELIMITER, "..."):
            return end
    return 0


def _iter_lines(text: str) -> Iterator[Tuple[int, int, str]]:
    offset = 0
    for line in text.splitlines(keepends=True):
        yield offset, offset + len(line), line
        offset += len(line)


def _merge(spans: List[Span]) -> List[Span]:
    """Sort and merge overlapping or adjacent spans."""

    merged: List[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged
