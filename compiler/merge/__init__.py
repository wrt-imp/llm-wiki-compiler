"""Stage 4 of the LLM Wiki Compiler: Semantic Merge.

Turns the Knowledge IR of several documents into one KnowledgeBase::

    >>> from compiler.merge import merge_knowledge_bases
    >>> knowledge_base = merge_knowledge_bases([ir_a, ir_b], judge)

Four stages: normalize (pure code), candidate matching (cheap rules), semantic
judge (LLM answers ``{"same": ...}``), merge (canonical names, merged
descriptions and sources, duplicate facts and relations removed).

Input is always existing Knowledge IRs - nothing is re-parsed or re-extracted.
Wiki generation, link resolution, search, graph and lint are not implemented.
"""

from .candidates import (
    DEFAULT_MAX_JUDGEMENTS,
    CandidatePair,
    auto_merge_groups,
    find_candidate_pairs,
)
from .errors import InvalidJudgeResponseError, MergeError
from .judge import JudgeVerdict, LLMJudge, SemanticJudge, verdict_from_payload
from .merger import (
    ON_ERROR_RAISE,
    ON_ERROR_SKIP,
    Merger,
    merge_knowledge_bases,
    merge_sources,
)
from .normalize import (
    alias_keys,
    compact_key,
    match_key,
    similarity,
    statement_key,
    tokens,
)
from .prompt import JUDGE_PROMPT_VERSION, JUDGE_SYSTEM_PROMPT, build_judge_prompt

__all__ = [
    "CandidatePair",
    "DEFAULT_MAX_JUDGEMENTS",
    "InvalidJudgeResponseError",
    "JUDGE_PROMPT_VERSION",
    "JUDGE_SYSTEM_PROMPT",
    "JudgeVerdict",
    "LLMJudge",
    "MergeError",
    "Merger",
    "ON_ERROR_RAISE",
    "ON_ERROR_SKIP",
    "SemanticJudge",
    "alias_keys",
    "auto_merge_groups",
    "build_judge_prompt",
    "compact_key",
    "find_candidate_pairs",
    "match_key",
    "merge_knowledge_bases",
    "merge_sources",
    "similarity",
    "statement_key",
    "tokens",
    "verdict_from_payload",
]
