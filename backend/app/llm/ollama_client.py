from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from app.config import settings
from app.llm.base import LLMError


class OllamaClient:
    def __init__(self):
        self.host = settings.ollama_host
        self.model = settings.ollama_model

    def _payload(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1024) -> str:
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(f"{self.host}/api/chat", json=self._payload(messages, temperature, max_tokens, False))
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.host} ({exc}). Is `ollama serve` running and has "
                f"`ollama pull {self.model}` been run?"
            ) from exc

    def stream(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1024) -> Iterator[str]:
        try:
            with httpx.Client(timeout=120.0) as client:
                with client.stream(
                    "POST", f"{self.host}/api/chat", json=self._payload(messages, temperature, max_tokens, True)
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        obj = json.loads(line)
                        chunk = obj.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                        if obj.get("done"):
                            break
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.host} ({exc}). Is `ollama serve` running and has "
                f"`ollama pull {self.model}` been run?"
            ) from exc
