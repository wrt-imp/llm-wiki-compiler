"""Stage 7 of the LLM Wiki Compiler: Search.

Keyword search over the generated wiki directory, standard library only::

    >>> from compiler.search import search_wiki
    >>> results = search_wiki("wiki", "解析器")
    >>> results[0].path
    '解析器.md'

An :class:`~compiler.search.indexer.SearchIndex` is built by reading the
Markdown pages (never the original sources, never the KnowledgeBase), and
queries match titles, aliases and body text with deterministic ordering. No
LLM, no embeddings, no external service, and nothing is written back.
"""

from .errors import SearchError
from .frontmatter import FrontMatter, as_list, parse_front_matter
from .index import (
    INDEXER_VERSION,
    KIND_CONCEPT,
    KIND_ENTITY,
    KIND_INDEX,
    KIND_PAGE,
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
from .indexer import (
    DEFAULT_ENCODING,
    DEFAULT_EXTENSION,
    build_page,
    display_text,
    extract_title,
    index_wiki,
)
from .query import (
    DEFAULT_SNIPPET_WINDOW,
    make_snippet,
    score_page,
    search,
    search_terms,
    search_wiki,
)

__all__ = [
    "DEFAULT_ENCODING",
    "DEFAULT_EXTENSION",
    "DEFAULT_SNIPPET_WINDOW",
    "FrontMatter",
    "INDEXER_VERSION",
    "KIND_CONCEPT",
    "KIND_ENTITY",
    "KIND_INDEX",
    "KIND_PAGE",
    "MATCH_ORDER",
    "SCORE_ALIAS_EXACT",
    "SCORE_ALIAS_CONTAINS",
    "SCORE_BODY_CONTAINS",
    "SCORE_TITLE_CONTAINS",
    "SCORE_TITLE_EXACT",
    "SearchError",
    "SearchIndex",
    "SearchPage",
    "SearchResult",
    "as_list",
    "build_page",
    "display_text",
    "extract_title",
    "index_wiki",
    "make_snippet",
    "normalize",
    "normalize_with_map",
    "parse_front_matter",
    "score_page",
    "search",
    "search_terms",
    "search_wiki",
]
