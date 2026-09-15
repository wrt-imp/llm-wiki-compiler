"""Stable file names for wiki pages.

Rules, in order:

1. the object's own name is the base, so Chinese titles stay readable
   (``编程语言`` -> ``编程语言.md``);
2. characters that are illegal on Windows/macOS/Linux are replaced by ``-``;
3. trailing dots/spaces are dropped and Windows reserved device names get a
   ``_`` prefix;
4. very long names are truncated and suffixed with the object id;
5. collisions are resolved case-insensitively (``Python.md`` and ``python.md``
   are the same file on Windows), deterministically, by adding the kind and
   then the object id.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

DEFAULT_EXTENSION = ".md"

#: Longest base name kept before truncation (characters, not bytes).
MAX_STEM_LENGTH = 80

#: Windows device names that cannot be used as a file name.
RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)

_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_DASH_RE = re.compile(r"-{2,}")
_FALLBACK_STEM = "page"


@dataclass(frozen=True)
class PageTarget:
    """A knowledge object that should get its own page."""

    kind: str
    object_id: str
    title: str
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WikiPage:
    """One generated page: where it lives and which object it describes."""

    path: str
    kind: str
    object_id: str
    title: str
    aliases: Tuple[str, ...] = ()


def safe_stem(name: str, *, object_id: str = "") -> str:
    """Return a filesystem safe base name (without extension)."""

    text = str(name or "").replace("\u00a0", " ").strip()
    text = _ILLEGAL_RE.sub("-", text)
    text = _DASH_RE.sub("-", text)
    text = text.strip().lstrip(".").rstrip(" .")
    if not text or not text.strip("-."):
        return _FALLBACK_STEM
    if len(text) > MAX_STEM_LENGTH:
        suffix = (object_id[:8] if object_id else _short_hash(text))
        keep = max(MAX_STEM_LENGTH - len(suffix) - 1, 1)
        text = text[:keep].rstrip() + "-" + suffix
    if text.casefold() in RESERVED_STEMS:
        text = "_" + text
    return text


def page_filename(
    name: str,
    *,
    kind: str,
    object_id: str,
    extension: str = DEFAULT_EXTENSION,
) -> str:
    """File name for a single page, ignoring collisions."""

    return safe_stem(name, object_id=object_id) + extension


def assign_page_paths(
    targets: Sequence[PageTarget],
    *,
    extension: str = DEFAULT_EXTENSION,
    reserved: Iterable[str] = (),
) -> List[WikiPage]:
    """Give every target a unique relative path.

    Args:
        targets: Objects that need a page, in the order they should be written.
        extension: File extension, ``.md`` by default.
        reserved: Stem names that are already taken (for example ``index``).

    Returns:
        One :class:`WikiPage` per target, in the same order.
    """

    stems = [safe_stem(target.title, object_id=target.object_id) for target in targets]

    counts: Dict[str, int] = {}
    for stem in stems:
        key = stem.casefold()
        counts[key] = counts.get(key, 0) + 1

    used: Dict[str, str] = {
        str(name).casefold(): "<reserved>" for name in reserved if str(name)
    }
    pages: List[WikiPage] = []
    for target, stem in zip(targets, stems):
        style = stem if counts[stem.casefold()] == 1 else f"{stem}-{target.kind}"
        candidate = style
        key = candidate.casefold()
        if key in used:
            suffix = target.object_id[:8] or _short_hash(f"{stem}-{target.kind}")
            candidate = f"{style}-{suffix}"
            key = candidate.casefold()
            attempt = 2
            while key in used:
                candidate = f"{style}-{suffix}-{attempt}"
                key = candidate.casefold()
                attempt += 1
        used[key] = target.object_id
        pages.append(
            WikiPage(
                path=candidate + extension,
                kind=target.kind,
                object_id=target.object_id,
                title=target.title,
                aliases=tuple(target.aliases),
            )
        )
    return pages


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
