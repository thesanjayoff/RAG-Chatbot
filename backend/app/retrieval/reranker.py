"""Cross-encoder reranker. Always runs locally (it's a small model, fast
enough on CPU) regardless of which LLM/embedding provider is configured,
so reranking quality never depends on an external API being reachable.
"""
from __future__ import annotations

import threading

from app.config import settings

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import CrossEncoder

                _model = CrossEncoder(settings.reranker_model)
    return _model


def rerank(query: str, candidates: list[dict], text_key: str = "text") -> list[dict]:
    if not candidates:
        return []
    if not settings.use_reranker:
        return sorted(candidates, key=lambda c: c.get("fused_score", c.get("score", 0.0)), reverse=True)
    model = _get_model()
    pairs = [(query, c[text_key]) for c in candidates]
    scores = model.predict(pairs)
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
