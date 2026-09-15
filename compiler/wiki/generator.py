"""Write a KnowledgeBase out as a Markdown wiki.

The whole wiki is rendered in memory first and only then written, so a
rendering problem can never leave a half written directory behind. Output is
UTF-8 with ``\\n`` line endings and contains no timestamps, which makes
repeated runs byte for byte identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from ..knowledge import KnowledgeBase
from .errors import WikiWriteError
from .paths import (
    DEFAULT_EXTENSION,
    PageTarget,
    WikiPage,
    assign_page_paths,
)
from .render import (
    GENERATOR_VERSION,
    WikiPlan,
    build_plan,
    render_index,
    render_page,
)

#: File name of the overview page.
INDEX_STEM = "index"


@dataclass
class WikiBuild:
    """What a generation run produced."""

    output_dir: Path
    pages: List[WikiPage] = field(default_factory=list)
    written: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WikiGenerator:
    """Compile one KnowledgeBase into Markdown pages."""

    def __init__(
        self,
        output_dir: Any,
        *,
        include_index: bool = True,
        front_matter: bool = True,
        overwrite: bool = True,
        extension: str = DEFAULT_EXTENSION,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.include_index = include_index
        self.front_matter = front_matter
        self.overwrite = overwrite
        self.extension = extension

    def generate(self, knowledge_base: KnowledgeBase) -> WikiBuild:
        """Render and write the wiki for ``knowledge_base``.

        Args:
            knowledge_base: Output of the Semantic Merge stage. Raw IRs, dicts
                and paths are rejected on purpose.

        Raises:
            TypeError: when the input is not a KnowledgeBase.
            WikiWriteError: when a file could not be written.
        """

        if not isinstance(knowledge_base, KnowledgeBase):
            raise TypeError(
                "WikiGenerator expects a KnowledgeBase, got "
                f"{type(knowledge_base).__name__}"
            )

        plan = build_plan(knowledge_base)
        pages = assign_page_paths(
            [_page_target(page_plan) for page_plan in plan.pages],
            extension=self.extension,
            reserved={INDEX_STEM} if self.include_index else set(),
        )

        contents: List[Tuple[str, str]] = [
            (
                page.path,
                render_page(page, page_plan, front_matter=self.front_matter),
            )
            for page, page_plan in zip(pages, plan.pages)
        ]
        if self.include_index:
            contents.append(
                (
                    INDEX_STEM + self.extension,
                    render_index(plan, pages, extension=self.extension),
                )
            )

        warnings = _warnings(plan, knowledge_base, self.include_index)
        written = self._write(contents)

        counts = dict(knowledge_base.counts())
        counts.update(
            {
                "pages": len(pages),
                "unattached_facts": len(plan.unattached_facts),
                "unattached_relations": len(plan.unattached_relations),
                "documents": len(plan.documents),
            }
        )
        return WikiBuild(
            output_dir=self.output_dir,
            pages=pages,
            written=written,
            counts=counts,
            metadata={
                "generator_version": GENERATOR_VERSION,
                "index_page": INDEX_STEM + self.extension if self.include_index else None,
                "options": {
                    "include_index": self.include_index,
                    "front_matter": self.front_matter,
                    "overwrite": self.overwrite,
                    "extension": self.extension,
                },
                "warnings": warnings,
            },
        )

    def _write(self, contents: Sequence[Tuple[str, str]]) -> List[str]:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WikiWriteError(
                f"cannot create wiki directory '{self.output_dir}': {exc}"
            ) from exc

        written: List[str] = []
        for relative, text in contents:
            target = self.output_dir / relative
            if target.exists() and not self.overwrite:
                raise WikiWriteError(
                    f"wiki page already exists and overwrite is disabled: '{target}'"
                )
            try:
                target.write_text(text, encoding="utf-8", newline="\n")
            except OSError as exc:
                raise WikiWriteError(
                    f"cannot write wiki page '{target}': {exc}"
                ) from exc
            written.append(relative)
        return written


def generate_wiki(
    knowledge_base: KnowledgeBase,
    output_dir: Any,
    *,
    include_index: bool = True,
    front_matter: bool = True,
    overwrite: bool = True,
    extension: str = DEFAULT_EXTENSION,
) -> WikiBuild:
    """Convenience wrapper around :class:`WikiGenerator`."""

    return WikiGenerator(
        output_dir,
        include_index=include_index,
        front_matter=front_matter,
        overwrite=overwrite,
        extension=extension,
    ).generate(knowledge_base)


def _page_target(plan: Any) -> PageTarget:
    return PageTarget(
        kind=plan.target.kind,
        object_id=plan.target.object_id,
        title=plan.target.title,
        aliases=plan.target.aliases,
    )


def _warnings(
    plan: WikiPlan, knowledge_base: KnowledgeBase, include_index: bool
) -> List[str]:
    warnings: List[str] = []
    if not include_index and (plan.unattached_facts or plan.unattached_relations):
        warnings.append(
            f"{len(plan.unattached_facts)} fact(s) and "
            f"{len(plan.unattached_relations)} relation(s) are not attached to a "
            "page and the index page is disabled"
        )
    if not plan.pages:
        warnings.append("the knowledge base has no entity or concept pages to write")
    if knowledge_base.metadata.get("warnings"):
        warnings.append(
            f"the knowledge base carries {len(knowledge_base.metadata['warnings'])} "
            "merge warning(s); see its metadata"
        )
    return warnings
