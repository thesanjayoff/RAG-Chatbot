"""Hybrid retrieval: run dense (vector) and sparse (BM25) search in
parallel, fuse them with min-max normalized weighted scoring, then rerank
the fused candidate pool with a cross-encoder for the final order."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.retrieval import bm25_index, vectorstore
from app.retrieval.embeddings import embed_texts
from app.retrieval.reranker import rerank as rerank_candidates

VECTOR_WEIGHT = 0.5
BM25_WEIGHT = 0.5


@dataclass
class RetrievalFilter:
    document_ids: list[str] | None = None
    tag_names: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    def is_empty(self) -> bool:
        return not (self.document_ids or self.tag_names or self.date_from or self.date_to)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    document_id: str
    filename: str
    page_start: int | None
    page_end: int | None
    section: str | None
    vector_score: float = 0.0
    bm25_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float | None = None


def _resolve_allowed_document_ids(db: Session, flt: RetrievalFilter) -> set[str] | None:
    from app.models import Document, Tag

    if flt.is_empty():
        return None

    query = db.query(Document.id)
    if flt.tag_names:
        query = query.join(Document.tags).filter(Tag.name.in_(flt.tag_names))
    if flt.document_ids:
        query = query.filter(Document.id.in_(flt.document_ids))
    if flt.date_from:
        query = query.filter(Document.created_at >= flt.date_from)
    if flt.date_to:
        query = query.filter(Document.created_at <= flt.date_to)

    return {row[0] for row in query.all()}


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def retrieve(
    db: Session,
    query_text: str,
    flt: RetrievalFilter | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    from app.models import Chunk, Document

    flt = flt or RetrievalFilter()
    final_k = top_k or settings.retrieval_top_k_final
    allowed_doc_ids = _resolve_allowed_document_ids(db, flt)

    where = {"document_id": {"$in": list(allowed_doc_ids)}} if allowed_doc_ids is not None else None
    [query_vec] = embed_texts([query_text])
    vector_hits = vectorstore.query(query_vec, settings.retrieval_top_k_vector, where=where)

    allowed_chunk_ids = None
    if allowed_doc_ids is not None:
        rows = db.query(Chunk.id).filter(Chunk.document_id.in_(allowed_doc_ids)).all()
        allowed_chunk_ids = {r[0] for r in rows}
    bm25_hits = bm25_index.search(query_text, settings.retrieval_top_k_bm25, allowed_chunk_ids=allowed_chunk_ids)

    vector_scores = {h["chunk_id"]: h["score"] for h in vector_hits}
    bm25_scores = {cid: score for cid, score in bm25_hits}

    all_ids = set(vector_scores) | set(bm25_scores)
    if not all_ids:
        return []

    norm_vec = dict(zip(vector_scores.keys(), _normalize(list(vector_scores.values()))))
    norm_bm25 = dict(zip(bm25_scores.keys(), _normalize(list(bm25_scores.values()))))

    fused = {
        cid: VECTOR_WEIGHT * norm_vec.get(cid, 0.0) + BM25_WEIGHT * norm_bm25.get(cid, 0.0) for cid in all_ids
    }
    top_ids = sorted(fused, key=lambda c: fused[c], reverse=True)[: max(final_k * 4, 20)]

    chunk_rows = db.query(Chunk).filter(Chunk.id.in_(top_ids)).all()
    chunk_by_id = {c.id: c for c in chunk_rows}
    doc_ids = {c.document_id for c in chunk_rows}
    doc_rows = db.query(Document).filter(Document.id.in_(doc_ids)).all()
    doc_by_id = {d.id: d for d in doc_rows}

    candidates = []
    for cid in top_ids:
        chunk = chunk_by_id.get(cid)
        if chunk is None:
            continue
        doc = doc_by_id.get(chunk.document_id)
        candidates.append(
            {
                "chunk_id": cid,
                "text": chunk.text,
                "document_id": chunk.document_id,
                "filename": doc.filename if doc else "unknown",
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section": chunk.section,
                "vector_score": vector_scores.get(cid, 0.0),
                "bm25_score": bm25_scores.get(cid, 0.0),
                "fused_score": fused[cid],
            }
        )

    reranked = rerank_candidates(query_text, candidates)
    final = reranked[:final_k]

    return [
        RetrievedChunk(
            chunk_id=c["chunk_id"],
            text=c["text"],
            document_id=c["document_id"],
            filename=c["filename"],
            page_start=c["page_start"],
            page_end=c["page_end"],
            section=c["section"],
            vector_score=c["vector_score"],
            bm25_score=c["bm25_score"],
            fused_score=c["fused_score"],
            rerank_score=c.get("rerank_score"),
        )
        for c in final
    ]
