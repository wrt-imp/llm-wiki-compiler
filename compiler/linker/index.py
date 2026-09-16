"""The page index: name / alias -> WikiPage.

Every page is registered under its title and all of its aliases, normalized
with the same rules the rest of the pipeline uses (``match_key``), so
"Parser", "parser" and " parser " all resolve to the same page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..merge.normalize import alias_keys, match_key
from ..wiki import WikiBuild, WikiPage


@dataclass
class LinkIndex:
    """Resolvable names and the pages they belong to."""

    pages: Dict[str, WikiPage] = field(default_factory=dict)
    #: Keys claimed by more than one page (for example an entity and a concept
    #: with the same title); they are never linked automatically.
    ambiguous: Dict[str, List[WikiPage]] = field(default_factory=dict)

    def lookup(self, text: str) -> Optional[WikiPage]:
        """Return the page for a name, or ``None`` when unknown or ambiguous."""

        return self.pages.get(match_key(text))

    def is_ambiguous(self, text: str) -> bool:
        return match_key(text) in self.ambiguous

    def candidates(self, text: str) -> List[WikiPage]:
        return list(self.ambiguous.get(match_key(text), []))

    @property
    def keys(self) -> List[str]:
        """All resolvable keys, longest first (longest match wins)."""

        return sorted(self.pages, key=lambda key: (-len(key), key))

    @property
    def ambiguous_keys(self) -> List[str]:
        return sorted(self.ambiguous, key=lambda key: (-len(key), key))

    @property
    def all_keys(self) -> List[str]:
        """Every known name, including the ambiguous ones.

        The matcher needs these too: an ambiguous name must still be found so
        that it can be reported (or resolved by policy) instead of silently
        landing in neither bucket.
        """

        return sorted(
            {*self.pages, *self.ambiguous}, key=lambda key: (-len(key), key)
        )

    @property
    def paths(self) -> List[str]:
        """Every page path known to the index."""

        seen: List[str] = []
        for page in [*self.pages.values(), *_flatten(self.ambiguous.values())]:
            if page.path not in seen:
                seen.append(page.path)
        return seen


def build_link_index(build: WikiBuild) -> LinkIndex:
    """Build the resolution index from ``WikiBuild.pages``."""

    claims: Dict[str, List[WikiPage]] = {}
    for page in build.pages:
        for key in alias_keys(page.title, page.aliases):
            bucket = claims.setdefault(key, [])
            if all(other.path != page.path for other in bucket):
                bucket.append(page)

    pages = {key: bucket[0] for key, bucket in claims.items() if len(bucket) == 1}
    ambiguous = {key: bucket for key, bucket in claims.items() if len(bucket) > 1}
    return LinkIndex(pages=pages, ambiguous=ambiguous)


def _flatten(groups: Sequence[List[WikiPage]]) -> List[WikiPage]:
    return [page for group in groups for page in group]
