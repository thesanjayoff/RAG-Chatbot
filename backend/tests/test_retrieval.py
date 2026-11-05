from __future__ import annotations

import numpy as np
import pytest

from app.config import settings
from app.models import Chunk, Document
from app.retrieval import bm25_index, vectorstore
from app.retrieval.hybrid import RetrievalFilter, retrieve


def _fake_vector_for_text(text: str, dim: int = 16) -> list[float]:
    """Deterministic pseudo-embedding: documents sharing a keyword end up
    with similar vectors, without downloading a real embedding model."""
    rng = np.random.RandomState(abs(hash(frozenset(text.lower().split()))) % (2**31))
    base = rng.normal(size=dim)
    for word in ("revenue", "cat", "ocean", "python"):
        if word in text.lower():
            word_rng = np.random.RandomState(abs(hash(word)) % (2**31))
            base = base + word_rng.normal(size=dim) * 3
    return (base / np.linalg.norm(base)).tolist()


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    def fake_embed_texts(texts):
        return [_fake_vector_for_text(t) for t in texts]

    monkeypatch.setattr("app.retrieval.hybrid.embed_texts", fake_embed_texts)
    monkeypatch.setattr(settings, "use_reranker", False)


def _add_document_with_chunks(db, filename, chunk_texts, tags=None, doc_id=None):
    doc = Document(id=doc_id or filename, filename=filename, stored_path=f"/tmp/{filename}", file_type="txt", file_hash=filename, status="ready")
    db.add(doc)
    db.flush()
    chunk_rows = []
    for i, text in enumerate(chunk_texts):
        c = Chunk(document_id=doc.id, chunk_index=i, text=text, section=None, page_start=i + 1, page_end=i + 1, char_start=0, char_end=len(text))
        db.add(c)
        chunk_rows.append(c)
    db.commit()
    for c in chunk_rows:
        db.refresh(c)

    embeddings = [_fake_vector_for_text(t) for t in chunk_texts]
    metadatas = [{"document_id": doc.id, "filename": filename, "chunk_index": c.chunk_index, "page_start": c.page_start, "page_end": c.page_end, "section": ""} for c in chunk_rows]
    vectorstore.upsert_chunks([c.id for c in chunk_rows], chunk_texts, embeddings, metadatas)
    bm25_index.rebuild_index(db)
    return doc


def test_hybrid_retrieval_finds_relevant_chunk_by_keyword_and_semantics(db_session):
    _add_document_with_chunks(
        db_session, "finance.txt",
        ["The company's total revenue grew by 12% in Q3 driven by strong sales.", "The office cafeteria serves lunch at noon."],
    )
    _add_document_with_chunks(
        db_session, "animals.txt",
        ["The cat sat quietly on the warm windowsill all afternoon."],
    )

    results = retrieve(db_session, "How much did revenue grow?", top_k=3)
    assert results
    assert "revenue grew" in results[0].text


def test_retrieval_filter_by_document_id_excludes_other_documents(db_session):
    doc_a = _add_document_with_chunks(db_session, "a.txt", ["Revenue details about company A."])
    _add_document_with_chunks(db_session, "b.txt", ["Revenue details about company B."])

    flt = RetrievalFilter(document_ids=[doc_a.id])
    results = retrieve(db_session, "revenue", flt=flt, top_k=5)
    assert results
    assert all(r.document_id == doc_a.id for r in results)


def test_retrieval_filter_by_tag(db_session):
    from app.models import Tag

    doc_a = _add_document_with_chunks(db_session, "a.txt", ["Python programming best practices."])
    doc_b = _add_document_with_chunks(db_session, "b.txt", ["Python programming anti-patterns."])
    tag = Tag(name="favorites")
    doc_a.tags.append(tag)
    db_session.commit()

    flt = RetrievalFilter(tag_names=["favorites"])
    results = retrieve(db_session, "python", flt=flt, top_k=5)
    assert results
    assert all(r.document_id == doc_a.id for r in results)


def test_retrieval_returns_empty_when_corpus_is_empty(db_session):
    results = retrieve(db_session, "anything at all", top_k=5)
    assert results == []


def test_bm25_rebuild_reflects_deleted_document(db_session):
    doc = _add_document_with_chunks(db_session, "temp.txt", ["Ocean currents affect climate patterns globally."])
    results = retrieve(db_session, "ocean currents", top_k=5)
    assert results

    db_session.query(Chunk).filter_by(document_id=doc.id).delete()
    db_session.delete(doc)
    db_session.commit()
    vectorstore.delete_by_document(doc.id)
    bm25_index.rebuild_index(db_session)

    results_after = retrieve(db_session, "ocean currents", top_k=5)
    assert results_after == []
