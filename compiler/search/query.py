"""Query a SearchIndex: keywords in, ranked SearchResults out.

Keywords are matched as literal substrings (no regular expressions, so special
characters are safe), case and width insensitive, all terms are required, and
the result order is fully deterministic.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from .index import (
    MATCH_ORDER,
    SCORE_ALIAS_EXACT,
    SCORE_ALIAS_CONTAINS,
    SCORE_BODY_CONTAINS,
    SCORE_TITLE_CONTAINS,
    SCORE_TITLE_EXACT,
    SearchIndex,
    SearchPage,
    SearchResult,
    normalize,
    normalize_with_map,
)
from .indexer import DEFAULT_EXTENSION, index_wiki

#: Characters of context kept on each side of a match.
DEFAULT_SNIPPET_WINDOW = 80


def search(
    index: SearchIndex,
    query: str,
    *,
    limit: Optional[int] = None,
    snippet_window: int = DEFAULT_SNIPPET_WINDOW,
) -> List[SearchResult]:
    """Return the pages matching every keyword in ``query``.

    Args:
        index: The wiki index to search.
        query: One or more keywords; whitespace separated.
        limit: Optional maximum number of results.
        snippet_window: Context characters kept around a match.

    Raises:
        ValueError: when the query is empty.
    """

    terms = search_terms(query)
    phrase = normalize(query)
    results: List[SearchResult] = []
    for page in index.pages:
        score, matched_in = score_page(page, terms, phrase=phrase)
        if score <= 0:
            continue
        results.append(
            SearchResult(
                path=page.path,
                title=page.title,
                score=score,
                snippet=make_snippet(page, terms, window=snippet_window),
                kind=page.kind,
                object_id=page.object_id,
                matched_in=matched_in,
            )
        )

    results.sort(key=lambda result: (-result.score, result.path))
    return results[:limit] if limit is not None else results


def search_wiki(
    wiki_dir: Any,
    query: str,
    *,
    extension: str = DEFAULT_EXTENSION,
    limit: Optional[int] = None,
    snippet_window: int = DEFAULT_SNIPPET_WINDOW,
) -> List[SearchResult]:
    """Index ``wiki_dir`` and search it in one call."""

    index = index_wiki(wiki_dir, extension=extension)
    return search(index, query, limit=limit, snippet_window=snippet_window)


def search_terms(query: str) -> List[str]:
    """Normalized, whitespace separated keywords of a query."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    terms = normalize(query).split()
    if not terms:
        raise ValueError("query must contain at least one search term")
    return terms


def score_page(
    page: SearchPage, terms: Sequence[str], *, phrase: str = ""
) -> Tuple[int, Tuple[str, ...]]:
    """Score a page against every term, or ``(0, ())`` when one is missing.

    The whole query is tried as a phrase first, so a multi word alias such as
    "Document Model" still counts as an exact alias hit even though the
    individual words are scored separately otherwise.
    """

    if phrase:
        if phrase == page.normalized_title:
            return SCORE_TITLE_EXACT, ("title",)
        if phrase in page.normalized_aliases:
            return SCORE_ALIAS_EXACT, ("alias",)
        if phrase in page.normalized_title:
            return SCORE_TITLE_CONTAINS, ("title",)
        if phrase in page.normalized_text:
            return SCORE_BODY_CONTAINS, ("body",)

    score = 0
    matched = set()
    for term in terms:
        if term == page.normalized_title:
            score += SCORE_TITLE_EXACT
            matched.add("title")
        elif term in page.normalized_aliases:
            score += SCORE_ALIAS_EXACT
            matched.add("alias")
        elif term in page.normalized_title:
            score += SCORE_TITLE_CONTAINS
            matched.add("title")
        elif any(term in alias for alias in page.normalized_aliases):
            score += SCORE_ALIAS_CONTAINS
            matched.add("alias")
        elif term in page.normalized_text:
            score += SCORE_BODY_CONTAINS
            matched.add("body")
        else:
            return 0, ()
    return score, tuple(kind for kind in MATCH_ORDER if kind in matched)


def make_snippet(
    page: SearchPage,
    terms: Sequence[str],
    *,
    window: int = DEFAULT_SNIPPET_WINDOW,
) -> str:
    """A short piece of page text around the earliest keyword occurrence."""

    text = page.display_text
    if not text.strip():
        return ""

    normalized, offsets = normalize_with_map(text)
    hit = _first_hit(normalized, terms)
    if hit is None or not offsets:
        return _head_snippet(text, window)

    position, length = hit
    start = offsets[position]
    end = offsets[min(position + length - 1, len(offsets) - 1)] + 1
    return _clip(text, start, end, window)


def _first_hit(
    normalized: str, terms: Sequence[str]
) -> Optional[Tuple[int, int]]:
    best: Optional[Tuple[int, int]] = None
    for term in terms:
        position = normalized.find(term)
        if position < 0:
            continue
        if best is None or position < best[0]:
            best = (position, len(term))
    return best


def _clip(text: str, start: int, end: int, window: int) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = " ".join(text[left:right].split())
    if not snippet:
        return ""
    if left > 0:
        snippet = "…" + snippet
    if right < len(text):
        snippet = snippet + "…"
    return snippet


def _head_snippet(text: str, window: int) -> str:
    limit = max(window * 2, 1)
    snippet = " ".join(text[:limit].split())
    if not snippet:
        return ""
    return snippet + ("…" if len(text) > limit else "")
