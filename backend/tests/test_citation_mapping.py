from __future__ import annotations

import random

from app.services.citation import CitableChunk, StreamingCiteProcessor, looks_like_refusal, process_citations


def _chunk(chunk_id, filename="report.pdf", page=3, text="some passage text"):
    return CitableChunk(
        chunk_id=chunk_id, document_id=f"doc-{filename}", filename=filename, page_start=page, page_end=page,
        section="Finance", text=text,
    )


def test_process_citations_maps_known_chunks_and_numbers_in_order():
    retrieved = [_chunk("aaaaaaaa"), _chunk("bbbbbbbb")]
    answer = "Revenue grew 10%. {cite:aaaaaaaa} Costs fell. {cite:bbbbbbbb} Revenue again. {cite:aaaaaaaa}"
    cleaned, citations = process_citations(answer, retrieved)

    assert "{cite:" not in cleaned
    assert "[1]" in cleaned and "[2]" in cleaned
    assert len(citations) == 2  # same chunk cited twice -> one citation entry
    assert citations[0]["chunk_id"] == "aaaaaaaa"
    assert citations[0]["number"] == 1
    assert citations[1]["chunk_id"] == "bbbbbbbb"
    assert citations[1]["number"] == 2


def test_process_citations_drops_unknown_chunk_ids():
    retrieved = [_chunk("aaaaaaaa")]
    answer = "A real claim {cite:aaaaaaaa} and a fabricated one {cite:deadbeef00}."
    cleaned, citations = process_citations(answer, retrieved)
    assert len(citations) == 1
    assert "deadbeef00" not in cleaned
    assert "{cite:" not in cleaned


def test_looks_like_refusal_detects_standard_phrase():
    assert looks_like_refusal("I couldn't find that in your documents.")
    assert not looks_like_refusal("Revenue grew 10% [1].")


def test_streaming_processor_matches_batch_result_when_tag_split_across_tokens():
    retrieved = [_chunk("aaaaaaaa"), _chunk("bbbbbbbb")]
    full_answer = "Revenue grew 10%. {cite:aaaaaaaa} Costs fell 5%. {cite:bbbbbbbb}"

    rng = random.Random(42)
    tokens = []
    i = 0
    while i < len(full_answer):
        step = rng.randint(1, 4)
        tokens.append(full_answer[i : i + step])
        i += step

    processor = StreamingCiteProcessor(retrieved)
    streamed = "".join(processor.feed(t) for t in tokens)
    streamed += processor.finish()

    batch_cleaned, batch_citations = process_citations(full_answer, retrieved)

    assert streamed == batch_cleaned
    assert processor.citations == batch_citations


def test_streaming_processor_never_emits_partial_tag():
    retrieved = [_chunk("aaaaaaaa")]
    full_answer = "Before. {cite:aaaaaaaa} After."
    processor = StreamingCiteProcessor(retrieved)
    emitted = ""
    for ch in full_answer:
        emitted += processor.feed(ch)
        assert "{cite" not in emitted  # never a half-formed tag in emitted text
    emitted += processor.finish()
    assert emitted == "Before. [1] After."
