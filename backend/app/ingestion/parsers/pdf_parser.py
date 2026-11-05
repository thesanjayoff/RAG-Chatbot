"""PDF parsing via PyMuPDF (fitz): text, structure (headings via font-size
heuristics, tables via PyMuPDF's table finder), page numbers, and an OCR
fallback for pages that are actually scanned images with no text layer.

Hidden-text defense: any span rendered unreadably small, or in pure white
(a common way to hide text from a human reader while a parser still
extracts it), is stripped from the text that reaches the LLM and reported
as a warning.
"""
from __future__ import annotations

import logging

import fitz  # PyMuPDF

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError

logger = logging.getLogger(__name__)

MIN_READABLE_FONT_SIZE = 1.5
WHITE_COLOR_INT = (1 << 24) - 1  # 0xFFFFFF packed as PyMuPDF returns it
HEADING_SIZE_RATIO = 1.18
MIN_TEXT_CHARS_FOR_NON_SCAN = 25


def _rect_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    area_a = a.width * a.height
    if area_a <= 0:
        return 0.0
    return (inter.width * inter.height) / area_a


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    if not rows:
        return ""
    cleaned = [[(cell or "").strip().replace("\n", " ") for cell in row] for row in rows]
    header, *body = cleaned
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _body_font_size(size_char_counts: dict[float, int]) -> float:
    """Body text is whichever font size covers the most *characters* on
    the page, not just whichever size is "in the middle" -- a short
    heading plus one line of body text would otherwise confuse a plain
    median, since both are sampled with equal weight."""
    if not size_char_counts:
        return 10.0
    return max(size_char_counts, key=size_char_counts.get)


def parse_pdf(path: str, ocr_fn=None) -> ParsedDocument:
    """`ocr_fn(pil_image) -> str` is injected so this module stays
    independent of which OCR engine is configured."""
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not open PDF: {exc}") from exc

    blocks: list[ParsedBlock] = []
    warnings: list[str] = []
    used_ocr = False
    current_section: str | None = None

    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_num = page_index + 1

        try:
            table_finder = page.find_tables()
            tables = list(table_finder.tables)
        except Exception:  # noqa: BLE001  (table API varies across versions)
            tables = []
        table_rects = [fitz.Rect(t.bbox) for t in tables]

        raw = page.get_text("dict")
        # Only visible spans count towards the body-size estimate --
        # otherwise a long run of hidden/tiny-font injected text (which
        # can easily out-number the visible characters on a short page)
        # would skew body_size down and make every real paragraph look
        # "large" by comparison, misclassifying it all as headings.
        size_char_counts: dict[float, int] = {}
        for b in raw.get("blocks", []):
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    size = span.get("size", 0)
                    text = span.get("text", "")
                    if size < MIN_READABLE_FONT_SIZE or span.get("color", 0) == WHITE_COLOR_INT:
                        continue
                    size_char_counts[size] = size_char_counts.get(size, 0) + len(text)
        body_size = _body_font_size(size_char_counts)

        page_text_chars = 0
        hidden_spans_removed = 0

        for b in raw.get("blocks", []):
            if b.get("type") != 0:  # 0 = text block, 1 = image
                continue
            block_rect = fitz.Rect(b["bbox"])
            if any(_rect_overlap_ratio(block_rect, tr) > 0.6 for tr in table_rects):
                continue  # represented by the table block instead

            line_texts = []
            max_size = 0.0
            for line in b.get("lines", []):
                visible_spans = []
                for span in line.get("spans", []):
                    size = span.get("size", body_size)
                    color = span.get("color", 0)
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    if size < MIN_READABLE_FONT_SIZE or color == WHITE_COLOR_INT:
                        hidden_spans_removed += 1
                        continue
                    visible_spans.append(text)
                    max_size = max(max_size, size)
                if visible_spans:
                    line_texts.append("".join(visible_spans))

            block_text = "\n".join(line_texts).strip()
            if not block_text:
                continue
            page_text_chars += len(block_text)

            is_heading = (
                max_size >= body_size * HEADING_SIZE_RATIO
                and len(block_text) < 120
                and "\n" not in block_text
            )
            if is_heading:
                current_section = block_text
                blocks.append(ParsedBlock(text=block_text, page=page_num, section=current_section, block_type="heading"))
            else:
                blocks.append(ParsedBlock(text=block_text, page=page_num, section=current_section, block_type="paragraph"))

        for t in tables:
            try:
                rows = t.extract()
            except Exception:  # noqa: BLE001
                continue
            md = _table_to_markdown(rows)
            if md:
                blocks.append(ParsedBlock(text=md, page=page_num, section=current_section, block_type="table"))
                page_text_chars += len(md)

        if hidden_spans_removed:
            warnings.append(
                f"page {page_num}: removed {hidden_spans_removed} unreadable/hidden text span(s) "
                "(tiny font or white-on-white) before indexing"
            )

        if page_text_chars < MIN_TEXT_CHARS_FOR_NON_SCAN and ocr_fn is not None:
            pix = page.get_pixmap(dpi=200)
            img = pix_to_pil(pix)
            try:
                ocr_text = ocr_fn(img)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"page {page_num}: OCR failed ({exc})")
                ocr_text = ""
            if ocr_text.strip():
                used_ocr = True
                blocks.append(
                    ParsedBlock(text=ocr_text.strip(), page=page_num, section=current_section, block_type="paragraph")
                )

    page_count = doc.page_count
    doc.close()
    return ParsedDocument(blocks=blocks, page_count=page_count, used_ocr=used_ocr, warnings=warnings)


def pix_to_pil(pix: "fitz.Pixmap"):
    from PIL import Image

    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)
