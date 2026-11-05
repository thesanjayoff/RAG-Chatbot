from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.config import settings
from app.schemas import SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _public_settings() -> dict:
    return {
        "fully_local_mode": settings.fully_local_mode,
        "llm_provider": settings.llm_provider,
        "ollama_host": settings.ollama_host,
        "ollama_model": settings.ollama_model,
        "anthropic_model": settings.anthropic_model,
        "anthropic_key_configured": bool(settings.anthropic_api_key),
        "embedding_provider": settings.embedding_provider,
        "local_embedding_model": settings.local_embedding_model,
        "use_reranker": settings.use_reranker,
        "refusal_score_threshold": settings.refusal_score_threshold,
        "ocr_enabled": settings.ocr_enabled,
        "max_upload_mb": settings.max_upload_mb,
    }


@router.get("")
def get_settings():
    return _public_settings()


@router.put("")
def update_settings(body: SettingsUpdate):
    data = body.model_dump(exclude_unset=True)
    if "llm_provider" in data and data["llm_provider"] == "anthropic" and settings.fully_local_mode:
        return {"error": "fully_local_mode is on; disable it before switching to the anthropic provider"}
    for key, value in data.items():
        if value is not None:
            setattr(settings, key, value)
    return _public_settings()


@router.get("/health")
def health_check():
    ollama_ok = False
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.ollama_host}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:  # noqa: BLE001
        ollama_ok = False

    from app.retrieval import vectorstore

    try:
        vector_count = vectorstore.count()
    except Exception:  # noqa: BLE001
        vector_count = None

    return {
        "status": "ok",
        "ollama_reachable": ollama_ok,
        "vector_chunk_count": vector_count,
        "settings": _public_settings(),
    }
