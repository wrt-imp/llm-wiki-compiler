"""Link Resolution: turn page titles and aliases into internal links.

The resolver reads the pages the Wiki Generator wrote (``WikiBuild`` says which
ones) and rewrites only the prose: markdown structure, code, existing links and
(by default) the Sources section stay untouched. It never calls an LLM, never
touches the KnowledgeBase and never invents targets - a name that is not a
known page stays plain text, so a dead link cannot be produced.
"""

from __future__ import annotations

import posixpath
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..merge.normalize import match_key
from ..wiki import WikiBuild, WikiPage
from .errors import DeadLinkError, LinkWriteError
from .format import LINK_STYLE_MARKDOWN, LINK_STYLES, format_link, relative_target
from .index import LinkIndex, build_link_index
from .markdown import protected_spans

LINKER_VERSION = "link-resolver-v1"

#: Policies for a name claimed by several pages.
ON_AMBIGUOUS_SKIP = "skip"
ON_AMBIGUOUS_PREFER_ENTITY = "prefer_entity"

_CJK_RANGES = (
    "\u3400-\u4dbf"
    "\u4e00-\u9fff"
    "\uf900-\ufaff"
    "\u3040-\u30ff"
    "\uac00-\ud7af"
)
_CJK_RE = re.compile(f"[{_CJK_RANGES}]")


@dataclass(frozen=True)
class TextLinks:
    """Result of linking one text block."""

    text: str
    links: int = 0
    skipped_self: int = 0
    skipped_ambiguous: int = 0


@dataclass
class LinkResult:
    """What a link resolution run produced."""

    output_dir: Path
    files: List[str] = field(default_factory=list)
    links: int = 0
    counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LinkResolver:
    """Add internal markdown links to the pages of a :class:`WikiBuild`."""

    def __init__(
        self,
        *,
        style: str = LINK_STYLE_MARKDOWN,
        in_place: bool = True,
        output_dir: Any = None,
        link_sources: bool = False,
        allow_self_links: bool = False,
        on_ambiguous: str = ON_AMBIGUOUS_SKIP,
        extension: str = "md",
    ) -> None:
        if style not in LINK_STYLES:
            raise ValueError(
                f"unknown link style {style!r}; expected one of "
                f"{', '.join(LINK_STYLES)}"
            )
        if on_ambiguous not in (ON_AMBIGUOUS_SKIP, ON_AMBIGUOUS_PREFER_ENTITY):
            raise ValueError(
                "on_ambiguous must be 'skip' or 'prefer_entity', got "
                f"{on_ambiguous!r}"
            )
        self.style = style
        self.in_place = in_place
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.link_sources = link_sources
        self.allow_self_links = allow_self_links
        self.on_ambiguous = on_ambiguous
        self.extension = extension.lstrip(".")

    def resolve(self, build: WikiBuild) -> LinkResult:
        """Link the pages of ``build`` and write the result."""

        index = build_link_index(build)
        files = list(build.written) or [page.path for page in build.pages]
        target_dir = self.output_dir or build.output_dir
        added: List[Tuple[str, str]] = []

        linked_files: List[str] = []
        total_links = 0
        counts = {
            "files": 0,
            "links": 0,
            "skipped_self": 0,
            "skipped_ambiguous": 0,
            "dead_links": 0,
            "pages": len(build.pages),
        }

        for relative in files:
            source = build.output_dir / relative
            try:
                original = source.read_text(encoding="utf-8")
            except OSError as exc:
                raise LinkWriteError(
                    f"cannot read wiki page '{source}': {exc}"
                ) from exc

            linked = link_text(
                original,
                index,
                from_path=relative,
                style=self.style,
                extension=self.extension,
                link_sources=self.link_sources,
                allow_self_links=self.allow_self_links,
                on_ambiguous=self.on_ambiguous,
                on_link=lambda target, page=relative: added.append((page, target)),
            )
            self._write(target_dir, relative, linked.text)

            linked_files.append(relative)
            total_links += linked.links
            counts["links"] += linked.links
            counts["skipped_self"] += linked.skipped_self
            counts["skipped_ambiguous"] += linked.skipped_ambiguous
            counts["files"] += 1

        self._verify_targets(target_dir, added)
        return LinkResult(
            output_dir=target_dir,
            files=linked_files,
            links=total_links,
            counts=counts,
            metadata={
                "linker_version": LINKER_VERSION,
                "style": self.style,
                "in_place": self.in_place,
                "link_sources": self.link_sources,
                "allow_self_links": self.allow_self_links,
                "on_ambiguous": self.on_ambiguous,
                "index_size": len(index.pages),
                "ambiguous_names": sorted(index.ambiguous),
            },
        )

    def _write(self, target_dir: Path, relative: str, text: str) -> None:
        target = target_dir / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            raise LinkWriteError(
                f"cannot write linked page '{target}': {exc}"
            ) from exc

    def _verify_targets(
        self, target_dir: Path, added: Sequence[Tuple[str, str]]
    ) -> None:
        """Every link we created must point at a file that exists."""

        for from_path, target in added:
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(from_path), target)
            )
            if not (target_dir / resolved).is_file():
                raise DeadLinkError(
                    f"link in '{from_path}' points at '{target}', "
                    "which does not exist"
                )


def link_text(
    text: str,
    index: LinkIndex,
    *,
    from_path: str = "",
    style: str = LINK_STYLE_MARKDOWN,
    extension: str = "md",
    link_sources: bool = False,
    allow_self_links: bool = False,
    on_ambiguous: str = ON_AMBIGUOUS_SKIP,
    on_link: Optional[Callable[[str], None]] = None,
) -> TextLinks:
    """Link every known name in ``text`` (markdown aware, deterministic)."""

    pattern = name_pattern(index.all_keys, extension=extension)
    spans = protected_spans(text, skip_sources_section=not link_sources)
    stats = {"links": 0, "skipped_self": 0, "skipped_ambiguous": 0}

    def link_gap(gap: str) -> str:
        def replace(match: re.Match) -> str:
            written = match.group(0)
            key = match_key(written)
            page = index.pages.get(key)
            if page is None:
                page = _pick_ambiguous(index.ambiguous.get(key, []), on_ambiguous)
                if page is None:
                    stats["skipped_ambiguous"] += 1
                    return written
            if not allow_self_links and from_path and page.path == from_path:
                stats["skipped_self"] += 1
                return written
            stats["links"] += 1
            if on_link is not None:
                on_link(relative_target(from_path, page.path))
            return format_link(written, page.path, from_path=from_path, style=style)

        return pattern.sub(replace, gap)

    parts: List[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(link_gap(text[cursor:start]))
        parts.append(text[start:end])
        cursor = end
    parts.append(link_gap(text[cursor:]))

    return TextLinks(
        text="".join(parts),
        links=stats["links"],
        skipped_self=stats["skipped_self"],
        skipped_ambiguous=stats["skipped_ambiguous"],
    )


def resolve_wiki(build: WikiBuild, **options: Any) -> LinkResult:
    """Convenience wrapper around :class:`LinkResolver`."""

    return LinkResolver(**options).resolve(build)


def find_link_targets(text: str) -> List[str]:
    """Markdown link destinations in ``text`` (used by tests and checks)."""

    return [
        urllib.parse.unquote(match.group("target"))
        for match in re.finditer(r"\[[^\]]*\]\((?P<target>[^)]*)\)", text)
    ]


def name_pattern(keys: Sequence[str], *, extension: str = "md") -> re.Pattern:
    """Alternation of all known names, longest first, with boundary guards.

    CJK has no word boundaries: Chinese prose glues names to the next word
    ("使用解析器把文档编译成…"), so a CJK name is matched wherever it appears and
    the longest known name wins (a page named "解析器阶段" is preferred over
    "解析器"). ASCII names do need word boundaries, so "parser" does not match
    inside "parsers". Every alternative is also blocked when it is followed by
    a page extension, so file names written in the index stay plain text.
    """

    extensions = sorted({extension, "md", "markdown"})
    guards = "|".join(re.escape(item) for item in extensions if item)
    extension_guard = rf"(?!\.(?:{guards})\b)" if guards else ""

    alternatives: List[str] = []
    for key in sorted(keys, key=lambda item: (-len(item), item)):
        if not key:
            continue
        alternatives.append(
            f"{_left_guard(key)}{_body_pattern(key)}{_right_guard(key)}"
            f"{extension_guard}"
        )
    if not alternatives:
        return re.compile(r"(?!x)x")
    return re.compile("|".join(alternatives), re.IGNORECASE)


def _pick_ambiguous(
    candidates: Sequence[WikiPage], on_ambiguous: str
) -> Optional[WikiPage]:
    if on_ambiguous == ON_AMBIGUOUS_PREFER_ENTITY:
        for page in candidates:
            if page.kind == "entity":
                return page
    return None


def _body_pattern(key: str) -> str:
    tokens = key.split()
    if not tokens:
        return re.escape(key)
    return r"\s+".join(re.escape(token) for token in tokens)


def _left_guard(key: str) -> str:
    if _CJK_RE.match(key[0]):
        return ""
    return "(?<![0-9A-Za-z_])"


def _right_guard(key: str) -> str:
    if _CJK_RE.match(key[-1]):
        return ""
    return "(?![0-9A-Za-z_])"
