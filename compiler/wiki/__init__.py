"""Stage 5 of the LLM Wiki Compiler: the Wiki Generator.

Turns one KnowledgeBase into Markdown pages::

    >>> from compiler.wiki import generate_wiki
    >>> build = generate_wiki(knowledge_base, "wiki")
    >>> [page.path for page in build.pages]
    ['解析器.md']

The generator only writes readable pages; it never calls an LLM, never merges
knowledge and never creates links - not ``[[wiki links]]`` and not markdown
links. Internal linking is the Link Resolver's job, which runs on the
``WikiBuild`` this stage returns.
"""

from .errors import WikiError, WikiWriteError
from .generator import INDEX_STEM, WikiBuild, WikiGenerator, generate_wiki
from .paths import (
    DEFAULT_EXTENSION,
    MAX_STEM_LENGTH,
    RESERVED_STEMS,
    PageTarget,
    WikiPage,
    assign_page_paths,
    page_filename,
    safe_stem,
)
from .render import (
    GENERATOR_VERSION,
    KIND_CONCEPT,
    KIND_ENTITY,
    KIND_INDEX,
    MAX_QUOTE_CHARS,
    PagePlan,
    RelationSlot,
    WikiPlan,
    build_plan,
    ordered_sources,
    relation_text,
    render_index,
    render_page,
    source_line,
)

__all__ = [
    "DEFAULT_EXTENSION",
    "GENERATOR_VERSION",
    "INDEX_STEM",
    "KIND_CONCEPT",
    "KIND_ENTITY",
    "KIND_INDEX",
    "MAX_QUOTE_CHARS",
    "MAX_STEM_LENGTH",
    "PagePlan",
    "PageTarget",
    "RESERVED_STEMS",
    "RelationSlot",
    "WikiBuild",
    "WikiError",
    "WikiGenerator",
    "WikiPage",
    "WikiPlan",
    "WikiWriteError",
    "assign_page_paths",
    "build_plan",
    "generate_wiki",
    "ordered_sources",
    "page_filename",
    "relation_text",
    "render_index",
    "render_page",
    "safe_stem",
    "source_line",
]
