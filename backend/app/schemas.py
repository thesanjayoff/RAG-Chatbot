from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FilterSpec(BaseModel):
    document_ids: list[str] | None = None
    tag_names: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    filters: FilterSpec | None = None
    show_chunks: bool = False
    allow_general_knowledge: bool = False
    use_subquestions: bool = False


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ConversationUpdate(BaseModel):
    title: str


class SummarizeRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)


class CompareRequest(BaseModel):
    document_ids_a: list[str] = Field(min_length=1)
    document_ids_b: list[str] = Field(min_length=1)
    aspect: str | None = None


class UrlIngestRequest(BaseModel):
    url: str
    tags: list[str] = Field(default_factory=list)


class WatchedFolderCreate(BaseModel):
    path: str
    recursive: bool = True


class SettingsUpdate(BaseModel):
    fully_local_mode: bool | None = None
    llm_provider: str | None = None
    ollama_model: str | None = None
    anthropic_model: str | None = None
    embedding_provider: str | None = None
    use_reranker: bool | None = None
    refusal_score_threshold: float | None = None
