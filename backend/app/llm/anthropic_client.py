from __future__ import annotations

from collections.abc import Iterator

from app.config import settings
from app.llm.base import LLMError


class AnthropicClient:
    def __init__(self):
        if settings.fully_local_mode:
            raise LLMError("Fully-local mode is on: refusing to construct an Anthropic client.")
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set. Add it to your .env to use the Anthropic provider.")
        import anthropic

        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    @staticmethod
    def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        rest = [m for m in messages if m["role"] != "system"]
        return "\n\n".join(system_parts), rest

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1024) -> str:
        system, rest = self._split_system(messages)
        resp = self.client.messages.create(
            model=self.model, system=system, messages=rest, temperature=temperature, max_tokens=max_tokens
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def stream(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1024) -> Iterator[str]:
        system, rest = self._split_system(messages)
        with self.client.messages.stream(
            model=self.model, system=system, messages=rest, temperature=temperature, max_tokens=max_tokens
        ) as stream:
            yield from stream.text_stream
