"""Central configuration. Everything that can vary between a user's machines
is read from environment variables (optionally via a .env file) so no secret
or path ever needs to be hardcoded."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

    # --- Networking ---
    # Bound to localhost by default: this app holds personal documents and is
    # not designed to be exposed beyond the machine it runs on.
    host: str = "127.0.0.1"
    port: int = 8731

    # --- Storage ---
    data_dir: Path = DEFAULT_DATA_DIR
    max_upload_mb: int = 100

    # --- Fully local mode ---
    # When true, no network call to a hosted provider (Anthropic, etc.) is
    # permitted anywhere in the app, regardless of other settings. Web-page
    # ingestion is also disabled in this mode since it requires outbound
    # network access.
    fully_local_mode: bool = False

    # --- Embeddings ---
    embedding_provider: Literal["local", "ollama"] = "local"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ollama_embedding_model: str = "nomic-embed-text"

    # --- Reranker (always local: a cross-encoder is small and fast enough
    # to run on CPU, and it never needs to leave the machine) ---
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    use_reranker: bool = True

    # --- LLM ---
    llm_provider: Literal["ollama", "anthropic"] = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b-instruct"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # --- Retrieval tuning ---
    chunk_target_tokens: int = 400
    chunk_overlap_tokens: int = 60
    retrieval_top_k_vector: int = 20
    retrieval_top_k_bm25: int = 20
    retrieval_top_k_final: int = 6
    refusal_score_threshold: float = 0.15  # below this reranked score -> "not found"
    allow_general_knowledge: bool = False  # user-togglable per-request too

    # --- OCR ---
    ocr_enabled: bool = True
    ocr_languages: str = "en"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def watch_config_path(self) -> Path:
        return self.data_dir / "watched_folders.json"

    def ensure_dirs(self) -> None:
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.vector_dir.mkdir(parents=True, exist_ok=True)

    def network_allowed(self) -> bool:
        """Single choke point other modules call before any outbound call."""
        return not self.fully_local_mode


settings = Settings()
settings.ensure_dirs()
