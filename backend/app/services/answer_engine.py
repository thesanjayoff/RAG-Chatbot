"""RAG orchestration: rewrite -> (optionally decompose) -> hybrid retrieve
-> rerank -> refusal check -> prompt -> generate -> citation mapping.
This is the one place that decides, deterministically, when the bot is
allowed to answer at all versus must say "I couldn't find that in your
documents."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.llm.base import LLMClient
from app.llm.prompts import build_answer_system_prompt
from app.retrieval.hybrid import RetrievalFilter, RetrievedChunk, retrieve
from app.retrieval.query_processing import maybe_decompose, rewrite_query
from app.security.sanitize import build_delimited_context
from app.services.citation import StreamingCiteProcessor, looks_like_refusal, process_citations

NOT_FOUND_MESSAGE = "I couldn't find that in your documents."


def _score(c: RetrievedChunk) -> float:
    return c.rerank_score if c.rerank_score is not None else c.fused_score


@dataclass
class RagContext:
    rewritten_query: str
    sub_questions: list[str] | None
    retrieved: list[RetrievedChunk]
    confidence: float
    is_low_confidence: bool
    messages: list[dict] | None  # None when short-circuited to a refusal
    delimiter_tag: str


def build_rag_context(
    db: Session,
    llm: LLMClient,
    history: list[dict[str, str]],
    question: str,
    flt: RetrievalFilter | None,
    use_subquestions: bool,
    allow_general_knowledge: bool,
) -> RagContext:
    rewritten = rewrite_query(llm, history, question)
    sub_questions = maybe_decompose(llm, rewritten) if use_subquestions else None
    queries = sub_questions if sub_questions else [rewritten]

    merged: dict[str, RetrievedChunk] = {}
    for q in queries:
        for rc in retrieve(db, q, flt):
            existing = merged.get(rc.chunk_id)
            if existing is None or _score(rc) > _score(existing):
                merged[rc.chunk_id] = rc

    retrieved = sorted(merged.values(), key=_score, reverse=True)[: settings.retrieval_top_k_final]
    confidence = _score(retrieved[0]) if retrieved else 0.0
    is_low_confidence = (not retrieved) or confidence < settings.refusal_score_threshold

    context_dicts = [
        {"source_id": c.chunk_id, "filename": c.filename, "page": c.page_start, "text": c.text} for c in retrieved
    ]
    context_text, tag = build_delimited_context(context_dicts) if context_dicts else ("", "DOCUMENT_DATA_NONE")
    system_prompt = build_answer_system_prompt(tag, allow_general_knowledge)

    messages: list[dict] | None
    if is_low_confidence and not allow_general_knowledge:
        messages = None
    else:
        history_messages = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
        if is_low_confidence:
            user_content = (
                f"(No sufficiently relevant document excerpts were found for this question.)\n\n"
                f"User question: {question}"
            )
        else:
            user_content = f"{context_text}\n\nUser question: {question}"
        messages = [{"role": "system", "content": system_prompt}, *history_messages, {"role": "user", "content": user_content}]

    return RagContext(
        rewritten_query=rewritten,
        sub_questions=sub_questions,
        retrieved=retrieved,
        confidence=confidence,
        is_low_confidence=is_low_confidence,
        messages=messages,
        delimiter_tag=tag,
    )


@dataclass
class AnswerResult:
    answer: str
    citations: list[dict]
    retrieved: list[RetrievedChunk]
    not_found: bool
    used_general_knowledge: bool
    rewritten_query: str
    sub_questions: list[str] | None


def answer_once(
    db: Session,
    llm: LLMClient,
    history: list[dict[str, str]],
    question: str,
    flt: RetrievalFilter | None = None,
    use_subquestions: bool = False,
    allow_general_knowledge: bool = False,
) -> AnswerResult:
    ctx = build_rag_context(db, llm, history, question, flt, use_subquestions, allow_general_knowledge)
    if ctx.messages is None:
        return AnswerResult(
            answer=NOT_FOUND_MESSAGE, citations=[], retrieved=ctx.retrieved, not_found=True,
            used_general_knowledge=False, rewritten_query=ctx.rewritten_query, sub_questions=ctx.sub_questions,
        )

    raw = llm.complete(ctx.messages, temperature=0.1, max_tokens=1500)
    cleaned, citations = process_citations(raw, ctx.retrieved)
    used_general_knowledge = "beyond your documents" in cleaned.lower()
    not_found = looks_like_refusal(cleaned) and not citations
    return AnswerResult(
        answer=cleaned, citations=citations, retrieved=ctx.retrieved, not_found=not_found,
        used_general_knowledge=used_general_knowledge, rewritten_query=ctx.rewritten_query, sub_questions=ctx.sub_questions,
    )


def stream_answer(
    db: Session,
    llm: LLMClient,
    history: list[dict[str, str]],
    question: str,
    flt: RetrievalFilter | None = None,
    use_subquestions: bool = False,
    allow_general_knowledge: bool = False,
) -> Iterator[dict]:
    """Yields event dicts: {"type": "meta"|"delta"|"citations"|"done", ...}"""
    ctx = build_rag_context(db, llm, history, question, flt, use_subquestions, allow_general_knowledge)
    yield {
        "type": "meta",
        "rewritten_query": ctx.rewritten_query,
        "sub_questions": ctx.sub_questions,
        "retrieved": [_chunk_to_dict(c) for c in ctx.retrieved],
        "low_confidence": ctx.is_low_confidence,
    }

    if ctx.messages is None:
        yield {"type": "delta", "text": NOT_FOUND_MESSAGE}
        yield {"type": "done", "citations": [], "not_found": True, "used_general_knowledge": False, "full_text": NOT_FOUND_MESSAGE}
        return

    processor = StreamingCiteProcessor(ctx.retrieved)
    full_text_parts: list[str] = []
    for token in llm.stream(ctx.messages, temperature=0.1, max_tokens=1500):
        safe_text = processor.feed(token)
        if safe_text:
            full_text_parts.append(safe_text)
            yield {"type": "delta", "text": safe_text}
    tail = processor.finish()
    if tail:
        full_text_parts.append(tail)
        yield {"type": "delta", "text": tail}

    full_text = "".join(full_text_parts).strip()
    used_general_knowledge = "beyond your documents" in full_text.lower()
    not_found = looks_like_refusal(full_text) and not processor.citations
    yield {
        "type": "done",
        "citations": processor.citations,
        "not_found": not_found,
        "used_general_knowledge": used_general_knowledge,
        "full_text": full_text,
    }


def _chunk_to_dict(c: RetrievedChunk) -> dict:
    return {
        "chunk_id": c.chunk_id,
        "document_id": c.document_id,
        "filename": c.filename,
        "page_start": c.page_start,
        "page_end": c.page_end,
        "section": c.section,
        "text": c.text,
        "vector_score": c.vector_score,
        "bm25_score": c.bm25_score,
        "fused_score": c.fused_score,
        "rerank_score": c.rerank_score,
    }
