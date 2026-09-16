"""Test support helpers: a scripted mock LLM client and sample payloads.

Imported by the extraction tests as ``from support import ...`` (pytest puts
the ``tests`` directory on ``sys.path``). Nothing here touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from compiler.knowledge import (
    Concept,
    Entity,
    Fact,
    KnowledgeBase,
    KnowledgeIR,
    Relation,
    SourceRef,
)
from compiler.merge import JudgeVerdict
from compiler.wiki import WikiBuild, generate_wiki
from compiler.linker import LinkResult, resolve_wiki

Response = Union[str, Exception]


class ScriptedLLMClient:
    """A mock ``LLMClient`` that returns queued answers and records prompts."""

    def __init__(self, *responses: Response, model: str = "mock-model") -> None:
        self._responses: List[Response] = list(responses)
        self.model = model
        self.calls: List[Tuple[str, str]] = []

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("ScriptedLLMClient ran out of scripted responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def last_system_prompt(self) -> str:
        return self.calls[-1][0]

    @property
    def last_user_prompt(self) -> str:
        return self.calls[-1][1]


def source(
    section_id: Optional[str] = None,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> Dict[str, Any]:
    """One ``sources`` entry as the model would emit it."""

    return {"section_id": section_id, "page_number": page_number, "quote": quote}


def sample_payload(
    section_id: Optional[str] = None,
    *,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> Dict[str, Any]:
    """A complete, valid extraction payload with one item of each kind."""

    src = [source(section_id, page_number, quote)]
    return {
        "entities": [
            {
                "name": "解析器",
                "type": "system",
                "description": "把源文件统一成 Document 的组件",
                "aliases": ["Parser"],
                "sources": src,
            }
        ],
        "concepts": [
            {
                "name": "文档模型",
                "description": "解析结果的结构化表示",
                "aliases": [],
                "sources": src,
            }
        ],
        "facts": [
            {
                "statement": "解析器把 PDF、Markdown、TXT 统一成 Document",
                "subject": "解析器",
                "predicate": "输出",
                "object": "Document",
                "sources": src,
            }
        ],
        "relations": [
            {
                "source": "解析器",
                "target": "文档模型",
                "type": "produces",
                "description": "解析器产出文档模型",
                "sources": src,
            }
        ],
    }


def payload_json(
    section_id: Optional[str] = None,
    *,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> str:
    """``sample_payload`` serialized the way a well behaved model would."""

    payload = sample_payload(section_id, page_number=page_number, quote=quote)
    return json.dumps(payload, ensure_ascii=False)


def empty_payload() -> Dict[str, Any]:
    """The answer for a document with no extractable knowledge."""

    return {"entities": [], "concepts": [], "facts": [], "relations": []}


# ----------------------------------------------------------------------
# Knowledge IR helpers (Semantic Merge tests)
# ----------------------------------------------------------------------
def src_ref(
    document_id: str,
    *,
    section_id: Optional[str] = None,
    page_number: Optional[int] = None,
    quote: str = "原文片段",
) -> SourceRef:
    """One source reference on an extracted item."""

    return SourceRef(
        document_id=document_id,
        section_id=section_id,
        page_number=page_number,
        quote=quote,
    )


def entity(
    name: str,
    *,
    type: str = "other",
    description: str = "",
    aliases: Tuple[str, ...] = (),
    sources: Tuple[SourceRef, ...] = (),
) -> Entity:
    return Entity(
        name=name,
        type=type,
        description=description,
        aliases=list(aliases),
        sources=list(sources),
    )


def concept(
    name: str,
    *,
    description: str = "",
    aliases: Tuple[str, ...] = (),
    sources: Tuple[SourceRef, ...] = (),
) -> Concept:
    return Concept(
        name=name,
        description=description,
        aliases=list(aliases),
        sources=list(sources),
    )


def fact(
    statement: str,
    *,
    subject: str = "",
    predicate: str = "",
    object: str = "",
    sources: Tuple[SourceRef, ...] = (),
) -> Fact:
    return Fact(
        statement=statement,
        subject=subject,
        predicate=predicate,
        object=object,
        sources=list(sources),
    )


def relation(
    source_name: str,
    target_name: str,
    *,
    type: str = "",
    description: str = "",
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    sources: Tuple[SourceRef, ...] = (),
) -> Relation:
    return Relation(
        source=source_name,
        target=target_name,
        type=type,
        description=description,
        source_id=source_id,
        target_id=target_id,
        sources=list(sources),
    )


def make_ir(
    document_id: str,
    *,
    title: Optional[str] = None,
    source: Optional[str] = None,
    entities: Tuple[Entity, ...] = (),
    concepts: Tuple[Concept, ...] = (),
    facts: Tuple[Fact, ...] = (),
    relations: Tuple[Relation, ...] = (),
) -> KnowledgeIR:
    """A per document Knowledge IR, as the extraction stage would produce it."""

    return KnowledgeIR(
        document_id=document_id,
        document_title=title if title is not None else f"title of {document_id}",
        source=source if source is not None else f"{document_id}.md",
        entities=list(entities),
        concepts=list(concepts),
        facts=list(facts),
        relations=list(relations),
    )


class ScriptedJudge:
    """A mock judge that returns queued verdicts and records the pairs."""

    def __init__(self, *verdicts: Union[JudgeVerdict, Exception]) -> None:
        self._verdicts: List[Union[JudgeVerdict, Exception]] = list(verdicts)
        self.calls: List[Tuple[str, str, str]] = []
        self.model = "scripted-judge"
        self.prompt_version = "test"

    def judge(self, kind: str, left: Any, right: Any) -> JudgeVerdict:
        self.calls.append((kind, left.name, right.name))
        if not self._verdicts:
            raise AssertionError("ScriptedJudge ran out of scripted verdicts")
        verdict = self._verdicts.pop(0)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict

    @property
    def call_names(self) -> List[Tuple[str, str, str]]:
        return list(self.calls)


# ----------------------------------------------------------------------
# KnowledgeBase helpers (Wiki Generator tests)
# ----------------------------------------------------------------------
def make_kb(
    *,
    entities: Tuple[Entity, ...] = (),
    concepts: Tuple[Concept, ...] = (),
    facts: Tuple[Fact, ...] = (),
    relations: Tuple[Relation, ...] = (),
    documents: Tuple[Dict[str, Any], ...] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> KnowledgeBase:
    """A unified KnowledgeBase, as Semantic Merge would produce it."""

    return KnowledgeBase(
        entities=list(entities),
        concepts=list(concepts),
        facts=list(facts),
        relations=list(relations),
        documents=[dict(document) for document in documents],
        metadata=dict(metadata or {}),
    )


def document_info(document_id: str, **overrides: Any) -> Dict[str, Any]:
    """One ``KnowledgeBase.documents`` entry."""

    info = {
        "id": document_id,
        "title": f"title of {document_id}",
        "source": f"{document_id}.md",
    }
    info.update(overrides)
    return info


# ----------------------------------------------------------------------
# Wiki helpers (Link Resolver tests)
# ----------------------------------------------------------------------
def wiki_kb() -> KnowledgeBase:
    """A small knowledge base whose prose mentions other knowledge objects."""

    return make_kb(
        entities=(
            entity(
                "解析器",
                type="system",
                description="把源文件统一成 Document 的组件",
                aliases=("Parser",),
                sources=(
                    src_ref("docA", section_id="docA#1", quote="解析器把 PDF 统一成 Document"),
                ),
            ),
            entity(
                "知识图谱编译器",
                type="system",
                description="使用解析器把文档编译成 wiki 的系统",
                sources=(src_ref("docA", section_id="docA#2", quote="知识图谱编译器"),),
            ),
        ),
        concepts=(
            concept(
                "文档模型",
                description="解析器的输出结构",
                aliases=("Document Model",),
                sources=(src_ref("docA", section_id="docA#3", quote="文档模型"),),
            ),
        ),
        facts=(
            fact(
                "解析器输出文档模型",
                subject="解析器",
                object="文档模型",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器输出文档模型"),),
            ),
            fact("知识图谱编译器使用解析器", subject="知识图谱编译器", object="解析器"),
        ),
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="produces",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器产出文档模型"),),
            ),
        ),
        documents=(document_info("docA"),),
    )


def build_sample_wiki(
    tmp_path: Path, kb: Optional[KnowledgeBase] = None, **options: Any
) -> WikiBuild:
    """Generate the sample wiki into ``tmp_path/wiki``."""

    return generate_wiki(
        kb if kb is not None else wiki_kb(), tmp_path / "wiki", **options
    )


def write_wiki_page(root: Path, relative: str, text: str) -> Path:
    """Write a hand made wiki page (used to test readers and indexers)."""

    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# ----------------------------------------------------------------------
# Lint helpers
# ----------------------------------------------------------------------
def clean_kb() -> KnowledgeBase:
    """A knowledge base where every page is linked and every item has a source."""

    return make_kb(
        entities=(
            entity(
                "解析器",
                type="system",
                description="把源文件统一成 Document 的组件",
                aliases=("Parser",),
                sources=(src_ref("docA", section_id="docA#1", quote="解析器"),),
            ),
            entity(
                "知识图谱编译器",
                type="system",
                description="把文档编译成 wiki 的系统",
                sources=(src_ref("docA", section_id="docA#2", quote="知识图谱编译器"),),
            ),
        ),
        concepts=(
            concept(
                "文档模型",
                description="解析器的输出结构",
                aliases=("Document Model",),
                sources=(src_ref("docA", section_id="docA#3", quote="文档模型"),),
            ),
        ),
        facts=(
            fact(
                "解析器输出文档模型",
                subject="解析器",
                predicate="输出",
                object="文档模型",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器输出文档模型"),),
            ),
        ),
        relations=(
            relation(
                "解析器",
                "文档模型",
                type="produces",
                sources=(src_ref("docA", section_id="docA#1", quote="解析器产出文档模型"),),
            ),
            relation(
                "知识图谱编译器",
                "解析器",
                type="uses",
                sources=(src_ref("docA", section_id="docA#2", quote="知识图谱编译器使用解析器"),),
            ),
            relation(
                "文档模型",
                "知识图谱编译器",
                type="describes",
                sources=(src_ref("docA", section_id="docA#3", quote="文档模型描述知识图谱编译器"),),
            ),
        ),
        documents=(document_info("docA"),),
    )


def clean_wiki(tmp_path: Path) -> Tuple[KnowledgeBase, WikiBuild, LinkResult]:
    """Generate and link the clean sample wiki."""

    knowledge_base = clean_kb()
    build = generate_wiki(knowledge_base, tmp_path / "wiki")
    result = resolve_wiki(build)
    return knowledge_base, build, result
