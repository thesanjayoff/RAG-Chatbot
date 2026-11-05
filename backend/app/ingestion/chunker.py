"""Structure-aware chunking: walk the parser's blocks (headings, paragraphs,
list items, tables) in document order and greedily pack them into chunks
near a target token budget, carrying a small overlap of trailing blocks
into the next chunk for context continuity across the split. Tables are
never split mid-row, and an oversized table is split by whole rows rather
than falling back to a blind character cut.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.ingestion.parsers.base import ParsedBlock


def estimate_tokens(text: str) -> int:
    """Rough chars-per-token heuristic. Good enough for sizing chunks; we
    deliberately avoid pulling in a tokenizer dependency for this."""
    return max(1, len(text) // 4)


@dataclass
class ChunkData:
    text: str
    section: str | None
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int
    token_count: int


def _split_table_block(block: ParsedBlock, target_tokens: int) -> list[ChunkData]:
    lines = block.text.split("\n")
    if len(lines) < 3:
        return [
            ChunkData(
                text=block.text, section=block.section, page_start=block.page, page_end=block.page,
                char_start=0, char_end=len(block.text), token_count=estimate_tokens(block.text),
            )
        ]
    header, separator, *rows = lines
    out: list[ChunkData] = []
    batch: list[str] = []
    batch_tokens = estimate_tokens(header) + estimate_tokens(separator)
    for row in rows:
        row_tokens = estimate_tokens(row)
        if batch and batch_tokens + row_tokens > target_tokens:
            text = "\n".join([header, separator, *batch])
            out.append(ChunkData(text=text, section=block.section, page_start=block.page, page_end=block.page, char_start=0, char_end=len(text), token_count=estimate_tokens(text)))
            batch = []
            batch_tokens = estimate_tokens(header) + estimate_tokens(separator)
        batch.append(row)
        batch_tokens += row_tokens
    if batch:
        text = "\n".join([header, separator, *batch])
        out.append(ChunkData(text=text, section=block.section, page_start=block.page, page_end=block.page, char_start=0, char_end=len(text), token_count=estimate_tokens(text)))
    return out


def chunk_blocks(
    blocks: list[ParsedBlock],
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[ChunkData]:
    target = target_tokens if target_tokens is not None else settings.chunk_target_tokens
    overlap = overlap_tokens if overlap_tokens is not None else settings.chunk_overlap_tokens

    blocks = [b for b in blocks if b.text.strip()]
    if not blocks:
        return []

    offsets: list[tuple[int, int]] = []
    pos = 0
    for b in blocks:
        start = pos
        end = start + len(b.text)
        offsets.append((start, end))
        pos = end + 2  # mirrors the "\n\n" join used when materializing chunk text

    chunks: list[ChunkData] = []
    cur: list[int] = []
    cur_tokens = 0

    def finalize() -> None:
        if not cur:
            return
        texts = [blocks[i].text for i in cur]
        text = "\n\n".join(texts)
        pages = [blocks[i].page for i in cur if blocks[i].page is not None]
        sections = [blocks[i].section for i in cur if blocks[i].section]
        chunks.append(
            ChunkData(
                text=text,
                section=sections[0] if sections else None,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                char_start=offsets[cur[0]][0],
                char_end=offsets[cur[-1]][1],
                token_count=estimate_tokens(text),
            )
        )

    i, n = 0, len(blocks)
    while i < n:
        block = blocks[i]
        btoks = estimate_tokens(block.text)

        if block.block_type == "table" and btoks > target * 1.5:
            finalize()
            cur, cur_tokens = [], 0
            chunks.extend(_split_table_block(block, target))
            i += 1
            continue

        if cur and cur_tokens + btoks > target:
            finalize()
            carry: list[int] = []
            carry_tokens = 0
            for j in reversed(cur):
                t = estimate_tokens(blocks[j].text)
                if carry_tokens + t > overlap:
                    break
                carry.insert(0, j)
                carry_tokens += t
            cur, cur_tokens = carry, carry_tokens

        cur.append(i)
        cur_tokens += btoks
        i += 1

    finalize()
    return chunks
