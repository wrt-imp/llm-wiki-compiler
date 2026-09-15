"""Prompt for the semantic judge.

The judge sees exactly two items and answers with one JSON object, so the LLM
is never asked to compare everything with everything.
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

#: Bumped whenever the judge wording changes; stored on every merge result.
JUDGE_PROMPT_VERSION = "merge-judge-v1"

_MAX_QUOTES = 3
_MAX_QUOTE_CHARS = 200

JUDGE_SYSTEM_PROMPT = """\
You decide whether two knowledge items extracted from documents are the SAME knowledge object.

Rules:
1. Answer "same": true only when both items denote the same entity or the same concept. Items that
   are merely related, similar, co-occurring or one level more general must be "same": false.
2. Judge only with the names, aliases, descriptions and source quotes given below. Do not use
   outside knowledge and do not guess.
3. The same object can be written differently: another language or script, an abbreviation, a
   spelling variant (for example "解析器" and "Parser", "Knowledge Graph" and "knowledge-graph").
4. Answer with ONE JSON object and nothing else: no markdown, no code fences, no explanation.
5. Keep "reason" short (at most 200 characters) and point at the evidence you used.

JSON shape:
{"same": true, "reason": "short explanation"}
"""


def build_judge_prompt(kind: str, left: Any, right: Any) -> Tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for one candidate pair."""

    lines: List[str] = [
        f"Kind: {kind}",
        "",
        _describe("Item A", left),
        "",
        _describe("Item B", right),
        "",
        f"Question: do Item A and Item B denote the same {kind}?",
    ]
    return JUDGE_SYSTEM_PROMPT, "\n".join(lines)


def _describe(label: str, item: Any) -> str:
    lines: List[str] = [label, f"name: {getattr(item, 'name', '')}"]
    item_type = getattr(item, "type", "")
    if item_type:
        lines.append(f"type: {item_type}")
    description = getattr(item, "description", "")
    if description:
        lines.append(f"description: {description}")
    aliases: Sequence[str] = getattr(item, "aliases", ()) or ()
    if aliases:
        lines.append("aliases: " + ", ".join(aliases))
    sources = list(getattr(item, "sources", ()) or ())[:_MAX_QUOTES]
    if sources:
        lines.append("sources:")
        for ref in sources:
            quote = " ".join(str(getattr(ref, "quote", "")).split())[:_MAX_QUOTE_CHARS]
            lines.append(f"- [document {ref.document_id}] {quote!r}")
    return "\n".join(lines)
