"""The ingestion pipeline: parse (sandboxed) -> hygiene (strip hidden
text, flag injection attempts, flag secrets/PII) -> structure-aware chunk
-> embed -> store (SQLite metadata + Chroma vectors + BM25 rebuild)."""
from __future__ import annotations

import logging
import traceback

from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion import sandbox
from app.ingestion.chunker import chunk_blocks
from app.ingestion.parsers.base import ParsedDocument, ParseError
from app.ingestion.parsers.dispatch import parse_document, parse_html_text
from app.retrieval import bm25_index, vectorstore
from app.retrieval.embeddings import embed_texts
from app.security.sanitize import clean_extracted_text
from app.security.secrets_scan import scan_text

logger = logging.getLogger(__name__)


def _remove_existing_chunks(db: Session, document_id: str) -> None:
    from app.models import Chunk

    db.query(Chunk).filter(Chunk.document_id == document_id).delete()
    vectorstore.delete_by_document(document_id)


def _store_parsed(db: Session, document, parsed: ParsedDocument) -> tuple[int, int, list[str]]:
    """Cleans block text, chunks it, embeds, and persists. Returns
    (chunk_count, injection_hits_count, warnings)."""
    from app.models import Chunk

    warnings = list(parsed.warnings)
    total_injection_hits: list[str] = []

    cleaned_blocks = []
    for block in parsed.blocks:
        cleaned_text, flags = clean_extracted_text(block.text)
        if flags["injection_phrases_found"]:
            total_injection_hits.extend(flags["injection_phrases_found"])
        block.text = cleaned_text
        if cleaned_text.strip():
            cleaned_blocks.append(block)

    chunks = chunk_blocks(cleaned_blocks)
    if not chunks:
        return 0, len(set(total_injection_hits)), warnings

    chunk_rows = []
    for idx, c in enumerate(chunks):
        row = Chunk(
            document_id=document.id,
            chunk_index=idx,
            text=c.text,
            section=c.section,
            page_start=c.page_start,
            page_end=c.page_end,
            char_start=c.char_start,
            char_end=c.char_end,
            token_count=c.token_count,
        )
        db.add(row)
        chunk_rows.append(row)
    db.flush()  # assign ids

    texts = [c.text for c in chunk_rows]
    embeddings = embed_texts(texts)
    metadatas = [
        {
            "document_id": document.id,
            "filename": document.filename,
            "chunk_index": row.chunk_index,
            "page_start": row.page_start if row.page_start is not None else -1,
            "page_end": row.page_end if row.page_end is not None else -1,
            "section": row.section or "",
        }
        for row in chunk_rows
    ]
    vectorstore.upsert_chunks([r.id for r in chunk_rows], texts, embeddings, metadatas)

    return len(chunk_rows), len(set(total_injection_hits)), warnings


def ingest_file(db: Session, document_id: str) -> None:
    from app.models import Document

    document = db.get(Document, document_id)
    if document is None:
        return

    document.status = "processing"
    document.progress = 0.05
    db.commit()

    try:
        if document.source_type == "url":
            with open(document.stored_path, encoding="utf-8", errors="replace") as fh:
                html = fh.read()
            parsed = sandbox.run_sandboxed(parse_html_text, html)
        else:
            parsed = sandbox.run_sandboxed(
                parse_document, document.file_type, document.stored_path, settings.ocr_enabled
            )
    except ParseError as exc:
        document.status = "error"
        document.error_message = str(exc)
        db.commit()
        return
    except Exception as exc:  # noqa: BLE001  (sandbox timeouts, crashes, etc.)
        logger.error("ingestion failed for %s: %s\n%s", document.filename, exc, traceback.format_exc())
        document.status = "error"
        document.error_message = f"parsing failed: {exc}"
        db.commit()
        return

    document.progress = 0.5
    db.commit()

    _remove_existing_chunks(db, document.id)

    try:
        chunk_count, injection_hits, warnings = _store_parsed(db, document, parsed)
    except Exception as exc:  # noqa: BLE001
        logger.error("embedding/storage failed for %s: %s\n%s", document.filename, exc, traceback.format_exc())
        document.status = "error"
        document.error_message = f"embedding/storage failed: {exc}"
        db.commit()
        return

    full_text = parsed.full_text()
    secrets_report = scan_text(full_text)

    document.page_count = parsed.page_count
    document.chunk_count = chunk_count
    document.used_ocr = parsed.used_ocr
    document.secrets_flag = secrets_report.has_secrets or secrets_report.has_pii
    document.secrets_summary = secrets_report.summary() or None
    document.injection_flag = injection_hits > 0
    document.injection_summary = (
        f"{injection_hits} distinct prompt-injection-style phrase pattern(s) detected in the text; "
        "they will never be followed as instructions." if injection_hits else None
    )
    document.error_message = "; ".join(warnings) if warnings and chunk_count else document.error_message
    document.status = "ready" if chunk_count > 0 else "error"
    if chunk_count == 0:
        document.error_message = document.error_message or "no extractable text was found in this file"
    document.progress = 1.0
    db.commit()

    bm25_index.rebuild_index(db)
