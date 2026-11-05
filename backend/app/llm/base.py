from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1024) -> str:
        ...

    def stream(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1024) -> Iterator[str]:
        ...
