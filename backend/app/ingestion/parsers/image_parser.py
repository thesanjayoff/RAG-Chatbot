"""Standalone image files (screenshots, photos of documents, scans) are
always OCR'd -- there is no text layer to fall back on."""
from __future__ import annotations

from PIL import Image

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError


def parse_image(path: str, ocr_fn) -> ParsedDocument:
    try:
        img = Image.open(path)
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not open image: {exc}") from exc

    text = ""
    if ocr_fn is not None:
        try:
            text = ocr_fn(img)
        except Exception as exc:  # noqa: BLE001
            return ParsedDocument(blocks=[], page_count=1, used_ocr=True, warnings=[f"OCR failed: {exc}"])

    blocks = []
    if text.strip():
        blocks.append(ParsedBlock(text=text.strip(), page=1, section=None, block_type="paragraph"))
    return ParsedDocument(blocks=blocks, page_count=1, used_ocr=True)
