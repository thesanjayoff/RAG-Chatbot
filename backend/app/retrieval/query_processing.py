"""Query rewriting (resolve follow-up pronouns/references using chat
history) and optional decomposition of a compound question into
sub-questions, both delegated to the configured LLM with small, cheap
prompts."""
from __future__ import annotations

import logging

from app.llm.base import LLMClient, LLMError
from app.llm.prompts import build_decompose_prompt, build_rewrite_prompt

logger = logging.getLogger(__name__)


def rewrite_query(llm: LLMClient, history: list[dict[str, str]], question: str) -> str:
    if not history:
        return question
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
    try:
        rewritten = llm.complete(build_rewrite_prompt(history_text, question), temperature=0.0, max_tokens=200)
        rewritten = rewritten.strip().strip('"')
        return rewritten or question
    except LLMError as exc:
        logger.warning("query rewrite failed, falling back to raw question: %s", exc)
        return question


def maybe_decompose(llm: LLMClient, question: str) -> list[str] | None:
    try:
        raw = llm.complete(build_decompose_prompt(question), temperature=0.0, max_tokens=200)
    except LLMError as exc:
        logger.warning("query decomposition failed: %s", exc)
        return None
    raw = raw.strip()
    if not raw or raw.upper().startswith("NONE"):
        return None
    sub_questions = [line.strip("-* ").strip() for line in raw.splitlines() if line.strip()]
    sub_questions = [q for q in sub_questions if len(q) > 3]
    if len(sub_questions) < 2:
        return None
    return sub_questions[:4]
