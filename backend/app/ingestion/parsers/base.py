"""Common data shapes every format-specific parser produces, so the
chunker and the rest of the ingestion pipeline never need to know which
parser a document came from."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedBlock:
    text: str
    page: int | None  # 1-indexed; None when the format has no concept of pages
    section: str | None  # nearest enclosing heading, if any
    block_type: str = "paragraph"  # heading | paragraph | table | list_item
    heading_level: int | None = None


@dataclass
class ParsedDocument:
    blocks: list[ParsedBlock]
    page_count: int = 0
    used_ocr: bool = False
    warnings: list[str] = field(default_factory=list)

    def full_text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())


class ParseError(Exception):
    pass
