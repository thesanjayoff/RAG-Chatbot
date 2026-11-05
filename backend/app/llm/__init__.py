from __future__ import annotations

from app.config import settings
from app.llm.base import LLMClient, LLMError


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "ollama":
        from app.llm.ollama_client import OllamaClient

        return OllamaClient()
    if settings.llm_provider == "anthropic":
        if settings.fully_local_mode:
            raise LLMError("Fully-local mode is on: the Anthropic provider is disabled. Switch LLM_PROVIDER to 'ollama'.")
        from app.llm.anthropic_client import AnthropicClient

        return AnthropicClient()
    raise LLMError(f"unknown LLM provider: {settings.llm_provider}")
