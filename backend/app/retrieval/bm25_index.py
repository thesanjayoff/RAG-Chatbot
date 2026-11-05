"""In-memory BM25 keyword index. rank_bm25 has no incremental-update API,
so we rebuild the whole index from SQLite whenever the chunk set changes.
For a personal document collection (thousands, not millions, of chunks)
a full rebuild takes well under a second and keeping it simple beats a
hand-rolled incremental inverted index.
"""
from __future__ import annotations

import re
import threading

from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

_lock = threading.Lock()
_bm25: BM25Okapi | None = None
_chunk_ids: list[str] = []


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def rebuild_index(db: Session) -> None:
    global _bm25, _chunk_ids
    from app.models import Chunk

    with _lock:
        rows = db.query(Chunk.id, Chunk.text).all()
        if not rows:
            _bm25 = None
            _chunk_ids = []
            return
        _chunk_ids = [r[0] for r in rows]
        corpus = [tokenize(r[1]) for r in rows]
        _bm25 = BM25Okapi(corpus)


def search(query: str, top_k: int, allowed_chunk_ids: set[str] | None = None) -> list[tuple[str, float]]:
    with _lock:
        if _bm25 is None or not _chunk_ids:
            return []
        scores = _bm25.get_scores(tokenize(query))
        chunk_ids = _chunk_ids
    ranked = sorted(zip(chunk_ids, scores), key=lambda x: x[1], reverse=True)
    if allowed_chunk_ids is not None:
        ranked = [r for r in ranked if r[0] in allowed_chunk_ids]
    ranked = [r for r in ranked if r[1] > 0]
    return ranked[:top_k]


def is_ready() -> bool:
    return _bm25 is not None
