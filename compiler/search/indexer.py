"""Build a SearchIndex from a wiki directory.

Only Markdown pages are read - never PDF, TXT or the KnowledgeBase - and the
files are never modified. Front matter is parsed and then dropped, so it can
never pollute a search for body text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List, Tuple

from .errors import SearchError
from .frontmatter import as_list, parse_front_matter
from .index import (
    INDEXER_VERSION,
    KIND_INDEX,
    KIND_PAGE,
    SearchIndex,
    SearchPage,
    normalize,
)

DEFAULT_EXTENSION = ".md"
DEFAULT_ENCODING = "utf-8"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<text>.+?)\s*#*\s*$", re.MULTILINE)
_HEADING_MARKER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(?P<text>.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)(?P<text>.+?)(?P=ticks)")
_MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\([^)]*\)")
_WIKI_LINK_RE = re.compile(r"\[\[(?P<text>[^\]]*)\]\]")


def index_wiki(
    wiki_dir: Any,
    *,
    extension: str = DEFAULT_EXTENSION,
    encoding: str = DEFAULT_ENCODING,
) -> SearchIndex:
    """Index every Markdown page below ``wiki_dir``.

    Raises:
        SearchError: when the directory does not exist or is not a directory.
    """

    root = Path(wiki_dir)
    if not root.exists():
        raise SearchError(f"wiki directory does not exist: '{root}'")
    if not root.is_dir():
        raise SearchError(f"wiki path is not a directory: '{root}'")

    suffix = extension if extension.startswith(".") else f".{extension}"
    warnings: List[str] = []
    skipped: List[str] = []
    pages: List[SearchPage] = []
    scanned = 0

    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        scanned += 1
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() != suffix.lower():
            skipped.append(relative)
            continue
        try:
            text, read_warning = _read_text(path, encoding)
        except OSError as exc:
            warnings.append(f"{relative}: cannot read file ({exc})")
            continue
        if read_warning:
            warnings.append(f"{relative}: {read_warning}")
        page, page_warnings = build_page(relative, text)
        pages.append(page)
        warnings.extend(page_warnings)

    return SearchIndex(
        root=root,
        pages=pages,
        metadata={
            "indexer_version": INDEXER_VERSION,
            "root": str(root),
            "extension": suffix,
            "files_scanned": scanned,
            "pages_indexed": len(pages),
            "skipped_files": skipped,
            "warnings": warnings,
        },
    )


def build_page(relative_path: str, text: str) -> Tuple[SearchPage, List[str]]:
    """Turn one Markdown document into an indexed page."""

    warnings: List[str] = []
    front = parse_front_matter(text)
    if front.warning:
        warnings.append(f"{relative_path}: {front.warning}")

    body = front.body
    stem = Path(relative_path).stem
    title = extract_title(body, stem)
    kind = str(front.data.get("kind") or "").strip()
    if not kind:
        kind = KIND_INDEX if stem == "index" else KIND_PAGE
    aliases = tuple(as_list(front.data.get("aliases")))
    display = display_text(body)
    normalized_aliases = tuple(
        key for key in (normalize(alias) for alias in aliases) if key
    )

    page = SearchPage(
        path=relative_path,
        title=title,
        kind=kind,
        object_id=str(front.data.get("id") or "").strip(),
        aliases=aliases,
        text=body,
        display_text=display,
        front_matter=dict(front.data),
        normalized_title=normalize(title),
        normalized_aliases=normalized_aliases,
        normalized_text=normalize(display),
    )
    return page, warnings


def extract_title(body: str, fallback: str) -> str:
    """First level one heading, else the first heading, else the file name."""

    first_heading = ""
    for match in _HEADING_RE.finditer(body):
        text = match.group("text").strip()
        if not text:
            continue
        if len(match.group(1)) == 1:
            return text
        if not first_heading:
            first_heading = text
    return first_heading or fallback


def display_text(body: str) -> str:
    """Page text with link targets and inline markup removed.

    Used for snippets (``](解析器.md)`` noise stays out of them); matching uses
    the same text so a query never hits link syntax only.
    """

    text = _MD_LINK_RE.sub(lambda match: match.group("text"), body)
    text = _WIKI_LINK_RE.sub(lambda match: match.group("text"), text)
    text = _INLINE_CODE_RE.sub(lambda match: match.group("text"), text)
    text = _BOLD_RE.sub(lambda match: match.group("text"), text)
    return _HEADING_MARKER_RE.sub("", text)


def _read_text(path: Path, encoding: str) -> Tuple[str, str]:
    data = path.read_bytes()
    try:
        return data.decode(encoding), ""
    except UnicodeDecodeError as exc:
        return data.decode(encoding, errors="replace"), (
            f"decoded with replacement characters ({exc.reason})"
        )
