"""Stage 6 of the LLM Wiki Compiler: Link Resolution.

Turns the pages written by the Wiki Generator into a linked wiki::

    >>> from compiler.wiki import generate_wiki
    >>> from compiler.linker import resolve_wiki
    >>> build = generate_wiki(knowledge_base, "wiki")
    >>> result = resolve_wiki(build)          # rewrites the pages in place
    >>> result.counts["links"]
    12

The resolver uses ``WikiBuild.pages`` as the page identity table, links names
and aliases with relative markdown links, and never creates a link to a page
that does not exist. It does not touch the KnowledgeBase and does not call an
LLM.
"""

from .errors import DeadLinkError, LinkerError, LinkWriteError
from .format import (
    LINK_STYLES,
    LINK_STYLE_MARKDOWN,
    LINK_STYLE_WIKI,
    encode_target,
    escape_display,
    format_link,
    relative_target,
)
from .index import LinkIndex, build_link_index
from .markdown import protected_spans
from .resolver import (
    LINKER_VERSION,
    ON_AMBIGUOUS_PREFER_ENTITY,
    ON_AMBIGUOUS_SKIP,
    LinkResolver,
    LinkResult,
    TextLinks,
    find_link_targets,
    link_text,
    name_pattern,
    resolve_wiki,
)

__all__ = [
    "DeadLinkError",
    "LINKER_VERSION",
    "LINK_STYLES",
    "LINK_STYLE_MARKDOWN",
    "LINK_STYLE_WIKI",
    "LinkIndex",
    "LinkResolver",
    "LinkResult",
    "LinkWriteError",
    "LinkerError",
    "ON_AMBIGUOUS_PREFER_ENTITY",
    "ON_AMBIGUOUS_SKIP",
    "TextLinks",
    "build_link_index",
    "encode_target",
    "escape_display",
    "find_link_targets",
    "format_link",
    "link_text",
    "name_pattern",
    "protected_spans",
    "relative_target",
    "resolve_wiki",
]
