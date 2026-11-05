"""Word (.docx) parsing via python-docx. Captures headings (by style),
paragraphs, lists, and tables. Word has an explicit "hidden text" run
property plus the usual tiny-font/white-font tricks -- all three are
stripped before the text reaches the LLM."""
from __future__ import annotations

from docx import Document as DocxDocument
from docx.table import Table as DocxTable

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError

MIN_READABLE_PT = 2.0


def _run_is_hidden(run) -> bool:
    try:
        if run.font.hidden:
            return True
        if run.font.size is not None and run.font.size.pt < MIN_READABLE_PT:
            return True
        if run.font.color and run.font.color.rgb is not None and str(run.font.color.rgb) == "FFFFFF":
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _visible_text(paragraph) -> tuple[str, int]:
    hidden_count = 0
    parts = []
    for run in paragraph.runs:
        if _run_is_hidden(run):
            if run.text.strip():
                hidden_count += 1
            continue
        parts.append(run.text)
    return "".join(parts), hidden_count


def _table_to_markdown(table: DocxTable) -> str:
    rows = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def parse_docx(path: str) -> ParsedDocument:
    try:
        doc = DocxDocument(path)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not open DOCX: {exc}") from exc

    blocks: list[ParsedBlock] = []
    warnings: list[str] = []
    current_section: str | None = None
    hidden_total = 0

    body_tables = iter(doc.tables)
    # Walk the document body in order so tables land between the
    # paragraphs that surround them, instead of all at the end.
    table_by_element_id = {t._tbl: t for t in doc.tables}
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            from docx.text.paragraph import Paragraph

            paragraph = Paragraph(child, doc)
            text, hidden_count = _visible_text(paragraph)
            hidden_total += hidden_count
            text = text.strip()
            if not text:
                continue
            style = (paragraph.style.name or "").lower() if paragraph.style else ""
            if style.startswith("heading") or style.startswith("title"):
                current_section = text
                level = 1
                digits = "".join(ch for ch in style if ch.isdigit())
                if digits:
                    level = int(digits)
                blocks.append(ParsedBlock(text=text, page=None, section=current_section, block_type="heading", heading_level=level))
            elif "list" in style:
                blocks.append(ParsedBlock(text=f"- {text}", page=None, section=current_section, block_type="list_item"))
            else:
                blocks.append(ParsedBlock(text=text, page=None, section=current_section, block_type="paragraph"))
        elif tag == "tbl" and child in table_by_element_id:
            md = _table_to_markdown(table_by_element_id[child])
            if md:
                blocks.append(ParsedBlock(text=md, page=None, section=current_section, block_type="table"))

    if hidden_total:
        warnings.append(f"removed {hidden_total} hidden/invisible text run(s) before indexing")

    return ParsedDocument(blocks=blocks, page_count=0, used_ocr=False, warnings=warnings)
