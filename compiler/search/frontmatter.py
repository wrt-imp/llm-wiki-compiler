"""Read the front matter the Wiki Generator writes.

Only the shape this project produces is understood - ``key: "value"`` lines and
an ``aliases:`` list of quoted strings - so no YAML dependency is needed. The
front matter is never part of the page text that gets searched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

FRONT_MATTER_DELIMITER = "---"


@dataclass
class FrontMatter:
    """Parsed front matter plus the body that follows it."""

    data: Dict[str, Any] = field(default_factory=dict)
    body: str = ""
    present: bool = False
    warning: str = ""


def parse_front_matter(text: str) -> FrontMatter:
    """Split ``text`` into front matter and body.

    A missing or unterminated ``---`` block is not an error: the whole text is
    returned as the body and a warning is reported.
    """

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return FrontMatter(body=text)

    closing: Optional[int] = None
    for index in range(1, len(lines)):
        if lines[index].strip() in (FRONT_MATTER_DELIMITER, "..."):
            closing = index
            break
    if closing is None:
        return FrontMatter(
            body=text,
            warning="front matter has no closing '---'; treated as body text",
        )

    data = parse_block(lines[1:closing])
    body = "".join(lines[closing + 1 :])
    return FrontMatter(data=data, body=body, present=True)


def parse_block(lines: Sequence[str]) -> Dict[str, Any]:
    """Parse the lines between the two ``---`` delimiters."""

    data: Dict[str, Any] = {}
    current_list: Optional[List[str]] = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_list is not None:
                current_list.append(_scalar(stripped[2:].strip()))
            continue
        key, separator, value = stripped.partition(":")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if not value:
            current_list = []
            data[key] = current_list
            continue
        current_list = None
        data[key] = _scalar(value)

    return data


def as_list(value: Any) -> List[str]:
    """Coerce a front matter value into a list of strings."""

    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return _unescape(text[1:-1])
    return text


def _unescape(text: str) -> str:
    """Undo the escaping the generator applies to quoted scalars."""

    if "\\" not in text:
        return text
    result: List[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            index += 1
            result.append(text[index])
        else:
            result.append(char)
        index += 1
    return "".join(result)
