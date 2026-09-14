"""Markdown parser (front matter plus heading structure)."""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Tuple

from .base import BaseParser, PathLike
from .document import FORMAT_MARKDOWN, Document

try:  # optional: used only for YAML front matter
    import yaml
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None

FRONT_MATTER_DELIMITER = "---"

_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_KEY_VALUE_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\s*:\s*(?P<value>.*)$")


class MarkdownParser(BaseParser):
    """Markdown -> Document.

    ``content`` is the markdown body with any YAML front matter removed; the
    parsed front matter, the heading outline and the character encoding are
    kept in ``metadata``.
    """

    format = FORMAT_MARKDOWN
    extensions = (".md", ".markdown")

    def parse(self, path: PathLike) -> Document:
        source = self._resolve_source(path)
        decoded = self._read_text(source)

        front_matter, body = split_front_matter(decoded.text)
        headings = extract_headings(body)

        title = _front_matter_title(front_matter)
        if not title and headings:
            title = headings[0]["text"]

        metadata: Dict[str, Any] = {
            "encoding": decoded.encoding,
            "had_decoding_errors": decoded.had_errors,
            "front_matter": front_matter,
            "headings": headings,
            "line_count": len(body.splitlines()),
        }
        return self._build_document(
            source, title=title, content=body, metadata=metadata
        )


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    """Split leading ``---`` front matter from the markdown body."""

    lines = text.split("\n")
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return {}, text

    for index in range(1, len(lines)):
        if lines[index].strip() in (FRONT_MATTER_DELIMITER, "..."):
            raw = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return parse_front_matter(raw), body

    # Unterminated front matter: treat the file as plain markdown.
    return {}, text


def parse_front_matter(raw: str) -> Dict[str, Any]:
    """Parse front matter text into a plain ``dict``.

    YAML is used when PyYAML is available; otherwise a minimal ``key: value``
    reader keeps nested templates working instead of failing.
    """

    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw)
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            return {str(key).strip(): _jsonable(value) for key, value in loaded.items()}

    result: Dict[str, Any] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(line)
        if match:
            result[match.group("key")] = match.group("value").strip().strip("\"'")
    return result


def extract_headings(body: str) -> List[Dict[str, Any]]:
    """Return the ATX heading outline, skipping fenced code blocks."""

    headings: List[Dict[str, Any]] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append(
                {
                    "level": len(match.group("hashes")),
                    "text": match.group("text").strip(),
                }
            )
    return headings


def _front_matter_title(front_matter: Dict[str, Any]) -> str:
    value = front_matter.get("title")
    return str(value).strip() if value is not None else ""


def _jsonable(value: Any) -> Any:
    """Convert YAML scalars into JSON friendly values."""

    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
