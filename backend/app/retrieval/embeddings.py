"""Embedding provider abstraction. "local" runs a sentence-transformers
model entirely on this machine (default, works with fully-local mode).
"ollama" calls a locally-running Ollama server -- still 100% on this
machine, so it is allowed even in fully-local mode; only truly external
hosted APIs are blocked by that flag (see app/llm/anthropic_client.py).
"""
from __future__ import annotations

import logging
import threading

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_local_model = None
_local_lock = threading.Lock()


def _get_local_model():
    global _local_model
    if _local_model is None:
        with _local_lock:
            if _local_model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading local embedding model %s", settings.local_embedding_model)
                _local_model = SentenceTransformer(settings.local_embedding_model)
    return _local_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.embedding_provider == "local":
        model = _get_local_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]
    if settings.embedding_provider == "ollama":
        return _embed_ollama(texts)
    raise ValueError(f"unknown embedding provider: {settings.embedding_provider}")


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    url = f"{settings.ollama_host}/api/embed"
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json={"model": settings.ollama_embedding_model, "input": texts})
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Ollama embedding call failed ({exc}). Is Ollama running and has "
            f"`ollama pull {settings.ollama_embedding_model}` been run?"
        ) from exc


def embedding_dimension() -> int:
    if settings.embedding_provider == "local":
        model = _get_local_model()
        return model.get_sentence_embedding_dimension()
    # Ollama models vary; probe with a throwaway embedding.
    vec = _embed_ollama(["dimension probe"])[0]
    return len(vec)
