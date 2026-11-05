"""Summarize-one-or-more-documents and compare-two-documents. Unlike chat
answering, these aren't query-driven: we take (a cap on) every chunk from
the selected document(s) in document order rather than running retrieval.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.llm.base import LLMClient
from app.llm.prompts import build_compare_system_prompt, build_summary_system_prompt
from app.security.sanitize import build_delimited_context
from app.services.citation import CitableChunk, process_citations

MAX_CHUNKS_PER_DOC = 60


def _load_chunks_for_docs(db: Session, document_ids: list[str]):
    from app.models import Chunk, Document

    chunks_by_doc = []
    for doc_id in document_ids:
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        rows = (
            db.query(Chunk)
            .filter(Chunk.document_id == doc_id)
            .order_by(Chunk.chunk_index)
            .limit(MAX_CHUNKS_PER_DOC)
            .all()
        )
        chunks_by_doc.append((doc, rows))
    return chunks_by_doc


def summarize_documents(db: Session, llm: LLMClient, document_ids: list[str]) -> dict:
    chunks_by_doc = _load_chunks_for_docs(db, document_ids)
    context_dicts = []
    retrieved_like = []
    for doc, rows in chunks_by_doc:
        for ch in rows:
            context_dicts.append({"source_id": ch.id, "filename": doc.filename, "page": ch.page_start, "text": ch.text})
            retrieved_like.append(
                CitableChunk(chunk_id=ch.id, document_id=doc.id, filename=doc.filename, page_start=ch.page_start, page_end=ch.page_end, section=ch.section, text=ch.text)
            )

    if not context_dicts:
        return {"summary": "No content was found in the selected document(s).", "citations": []}

    context_text, tag = build_delimited_context(context_dicts)
    system_prompt = build_summary_system_prompt(tag)
    names = ", ".join(doc.filename for doc, _ in chunks_by_doc)
    user_content = f"{context_text}\n\nSummarize the document(s) above ({names})."
    raw = llm.complete([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}], temperature=0.2, max_tokens=1800)
    cleaned, citations = process_citations(raw, retrieved_like)
    return {"summary": cleaned, "citations": citations}


def compare_documents(db: Session, llm: LLMClient, document_ids_a: list[str], document_ids_b: list[str], aspect: str | None = None) -> dict:
    chunks_a = _load_chunks_for_docs(db, document_ids_a)
    chunks_b = _load_chunks_for_docs(db, document_ids_b)

    context_dicts = []
    retrieved_like = []

    def add(chunks_by_doc, label):
        for doc, rows in chunks_by_doc:
            for ch in rows:
                context_dicts.append(
                    {"source_id": ch.id, "filename": f"[{label}] {doc.filename}", "page": ch.page_start, "text": ch.text}
                )
                retrieved_like.append(
                    CitableChunk(chunk_id=ch.id, document_id=doc.id, filename=doc.filename, page_start=ch.page_start, page_end=ch.page_end, section=ch.section, text=ch.text)
                )

    add(chunks_a, "Document A")
    add(chunks_b, "Document B")

    if not context_dicts:
        return {"comparison": "No content was found in the selected documents.", "citations": []}

    context_text, tag = build_delimited_context(context_dicts)
    system_prompt = build_compare_system_prompt(tag)
    question = aspect or "What differs between Document A and Document B, and what do they have in common?"
    user_content = f"{context_text}\n\n{question}"
    raw = llm.complete([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}], temperature=0.2, max_tokens=1800)
    cleaned, citations = process_citations(raw, retrieved_like)
    return {"comparison": cleaned, "citations": citations}
