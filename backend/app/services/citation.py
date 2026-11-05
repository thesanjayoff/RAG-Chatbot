"""Turns the model's inline {cite:<chunk_id>} tags into user-facing,
numbered, clickable citations. Any tag citing a chunk_id that was not
actually part of the retrieved context is silently dropped rather than
trusted -- the model cannot manufacture a citation to a document it
never saw.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm.prompts import CITE_TOKEN_PATTERN

_CITE_RE = re.compile(CITE_TOKEN_PATTERN)


@dataclass
class CitableChunk:
    """Minimal shape process_citations() needs. RetrievedChunk satisfies
    this structurally; document_tasks builds these directly for chunks
    that were loaded without going through retrieval."""

    chunk_id: str
    document_id: str
    filename: str
    page_start: int | None
    page_end: int | None
    section: str | None
    text: str

NOT_FOUND_PHRASES = [
    "couldn't find that in your documents",
    "could not find that in your documents",
    "i don't have that in your documents",
    "not found in your documents",
]


def process_citations(answer_text: str, retrieved: list["CitableChunk"]) -> tuple[str, list[dict]]:
    by_id = {c.chunk_id: c for c in retrieved}
    numbering: dict[str, int] = {}
    citations: list[dict] = []

    def repl(match: re.Match) -> str:
        chunk_id = match.group(1)
        chunk = by_id.get(chunk_id)
        if chunk is None:
            return ""
        if chunk_id not in numbering:
            numbering[chunk_id] = len(numbering) + 1
            citations.append(
                {
                    "number": numbering[chunk_id],
                    "chunk_id": chunk_id,
                    "document_id": chunk.document_id,
                    "filename": chunk.filename,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section": chunk.section,
                    "snippet": chunk.text[:400],
                }
            )
        return f"[{numbering[chunk_id]}]"

    cleaned = _CITE_RE.sub(repl, answer_text)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return cleaned.strip(), citations


def looks_like_refusal(answer_text: str) -> bool:
    lowered = answer_text.lower()
    return any(phrase in lowered for phrase in NOT_FOUND_PHRASES)


class StreamingCiteProcessor:
    """Incremental counterpart to process_citations(), used while tokens
    are still arriving from the LLM. Buffers text starting at the last
    unmatched '{' so a {cite:...} tag split across two streamed tokens is
    never shown to the user half-formed."""

    def __init__(self, retrieved: list["CitableChunk"]):
        self._by_id = {c.chunk_id: c for c in retrieved}
        self._numbering: dict[str, int] = {}
        self.citations: list[dict] = []
        self._buffer = ""

    def _replace_complete(self, text: str) -> str:
        def repl(match: re.Match) -> str:
            chunk_id = match.group(1)
            chunk = self._by_id.get(chunk_id)
            if chunk is None:
                return ""
            if chunk_id not in self._numbering:
                self._numbering[chunk_id] = len(self._numbering) + 1
                self.citations.append(
                    {
                        "number": self._numbering[chunk_id],
                        "chunk_id": chunk_id,
                        "document_id": chunk.document_id,
                        "filename": chunk.filename,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "section": chunk.section,
                        "snippet": chunk.text[:400],
                    }
                )
            return f"[{self._numbering[chunk_id]}]"

        return _CITE_RE.sub(repl, text)

    def feed(self, token: str) -> str:
        self._buffer += token
        idx = self._buffer.rfind("{")
        if idx == -1 or "}" in self._buffer[idx:]:
            safe, self._buffer = self._buffer, ""
        else:
            safe, self._buffer = self._buffer[:idx], self._buffer[idx:]
        return self._replace_complete(safe)

    def finish(self) -> str:
        remainder, self._buffer = self._buffer, ""
        return self._replace_complete(remainder)
