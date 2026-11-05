from __future__ import annotations

from app.ingestion.chunker import chunk_blocks, estimate_tokens
from app.ingestion.parsers.base import ParsedBlock


def _para(words: int, page=1, section=None, block_type="paragraph") -> ParsedBlock:
    text = " ".join(f"word{i}" for i in range(words))
    return ParsedBlock(text=text, page=page, section=section, block_type=block_type)


def test_chunks_respect_target_token_budget():
    blocks = [_para(80, section="S1") for _ in range(10)]  # ~80 words * ~5 chars/4 ≈ 100 tokens each
    chunks = chunk_blocks(blocks, target_tokens=150, overlap_tokens=20)
    assert len(chunks) > 1
    for c in chunks[:-1]:
        assert c.token_count <= 150 * 1.5  # single oversized block can't be split further here


def test_chunk_carries_overlap_from_previous_chunk():
    # Small blocks relative to the budget so more than one lands in a
    # chunk, and the trailing block is small enough to carry forward.
    blocks = [_para(10) for _ in range(6)]
    chunks = chunk_blocks(blocks, target_tokens=50, overlap_tokens=20)
    assert len(chunks) >= 2
    # The tail of chunk 1 should reappear at the head of chunk 2 (the overlap).
    tail_of_first = chunks[0].text.split("\n\n")[-1]
    assert tail_of_first in chunks[1].text


def test_heading_sets_section_for_following_blocks():
    blocks = [
        ParsedBlock(text="Revenue", page=1, section=None, block_type="heading"),
        _para(10, section="Revenue"),
        ParsedBlock(text="Costs", page=1, section=None, block_type="heading"),
        _para(10, section="Costs"),
    ]
    chunks = chunk_blocks(blocks, target_tokens=10000, overlap_tokens=0)
    assert len(chunks) == 1
    assert chunks[0].section == "Revenue"  # first block's section wins for this fused chunk


def test_page_range_spans_min_to_max():
    blocks = [_para(5, page=1), _para(5, page=2), _para(5, page=3)]
    chunks = chunk_blocks(blocks, target_tokens=10000, overlap_tokens=0)
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 3


def test_oversized_table_is_split_by_rows_not_mid_row():
    header = "| Name | Value |"
    sep = "| --- | --- |"
    rows = [f"| item{i} | {i * 100} |" for i in range(200)]
    table_text = "\n".join([header, sep, *rows])
    block = ParsedBlock(text=table_text, page=1, section="Data", block_type="table")

    chunks = chunk_blocks([block], target_tokens=200, overlap_tokens=0)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.startswith(header)
        assert sep in c.text
        for line in c.text.splitlines()[2:]:
            assert line.startswith("|") and line.endswith("|")


def test_estimate_tokens_monotonic():
    assert estimate_tokens("a" * 40) > estimate_tokens("a" * 10)
