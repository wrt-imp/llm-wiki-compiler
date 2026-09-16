"""Search data structures and text normalization.

Everything is plain standard library code: a page is a small record with the
text variants needed for matching and for snippets, and the index is a list of
those records in a deterministic order.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

#: Bumped whenever indexing changes; stored in ``SearchIndex.metadata``.
INDEXER_VERSION = "search-indexer-v1"

KIND_ENTITY = "entity"
KIND_CONCEPT = "concept"
KIND_INDEX = "index"
KIND_PAGE = "page"

#: Fixed weights - only used to order results, never as a real ranking model.
SCORE_TITLE_EXACT = 100
SCORE_ALIAS_EXACT = 50
SCORE_TITLE_CONTAINS = 10
SCORE_ALIAS_CONTAINS = 5
SCORE_BODY_CONTAINS = 1

#: Order used by ``SearchResult.matched_in``.
MATCH_ORDER = ("title", "alias", "body")


@dataclass(frozen=True)
class SearchPage:
    """One indexed wiki page."""

    path: str
    title: str
    kind: str
    object_id: str
    aliases: Tuple[str, ...] = ()
    #: Raw page text (front matter removed), kept for reference.
    text: str = ""
    #: Same text with link targets / code markers cleaned up - for snippets.
    display_text: str = ""
    front_matter: Dict[str, Any] = field(default_factory=dict)
    normalized_title: str = ""
    normalized_aliases: Tuple[str, ...] = ()
    #: Normalized ``display_text``; matching uses this field.
    normalized_text: str = ""


@dataclass(frozen=True)
class SearchResult:
    """One hit."""

    path: str
    title: str
    score: int
    snippet: str
    kind: str = ""
    object_id: str = ""
    matched_in: Tuple[str, ...] = ()


@dataclass
class SearchIndex:
    """All pages of a wiki directory, ready to be queried."""

    root: Path
    pages: List[SearchPage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def page(self, path: str) -> SearchPage:
        """Return the indexed page for a relative path."""

        for page in self.pages:
            if page.path == path:
                return page
        raise KeyError(path)


def normalize(text: str) -> str:
    """Normalize text for matching: width, case and whitespace.

    NFKC turns full width characters into their ASCII form, ``casefold`` makes
    matching case insensitive and whitespace runs (including newlines) become a
    single space, so a query can span a line break.
    """

    folded = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(folded.split())


def normalize_with_map(text: str) -> Tuple[str, List[int]]:
    """Like :func:`normalize`, but also return the source index per character.

    Snippets are cut out of the original text, so the position found in the
    normalized text has to be mapped back; NFKC and casefolding can change
    character counts.
    """

    pieces: List[str] = []
    offsets: List[int] = []
    pending_space = False

    for index, char in enumerate(str(text or "")):
        folded = unicodedata.normalize("NFKC", char).casefold()
        if not folded or not folded.strip():
            pending_space = True
            continue
        if pending_space and pieces:
            pieces.append(" ")
            offsets.append(index)
        pending_space = False
        for piece in folded:
            pieces.append(piece)
            offsets.append(index)

    return "".join(pieces), offsets
