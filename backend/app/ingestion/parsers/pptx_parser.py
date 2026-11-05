"""PowerPoint (.pptx) parsing via python-pptx. Each slide is treated as a
"page" for citation purposes. The slide title becomes the section heading
for everything else on that slide."""
from __future__ import annotations

from pptx import Presentation
from pptx.util import Pt

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError

MIN_READABLE_PT = 2.0


def _run_is_hidden(run) -> bool:
    try:
        font = run.font
        if font.size is not None and font.size <= Pt(MIN_READABLE_PT):
            return True
        if font.color and font.color.type is not None and str(font.color.rgb) == "FFFFFF":
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _table_to_markdown(table) -> str:
    rows = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def parse_pptx(path: str) -> ParsedDocument:
    try:
        prs = Presentation(path)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not open PPTX: {exc}") from exc

    blocks: list[ParsedBlock] = []
    warnings: list[str] = []
    hidden_total = 0

    for slide_index, slide in enumerate(prs.slides):
        page_num = slide_index + 1
        section = f"Slide {page_num}"

        title_shape = slide.shapes.title
        if title_shape is not None and title_shape.has_text_frame:
            title_text = title_shape.text_frame.text.strip()
            if title_text:
                section = title_text
                blocks.append(ParsedBlock(text=title_text, page=page_num, section=section, block_type="heading"))

        for shape in slide.shapes:
            if shape == title_shape:
                continue
            if shape.has_table:
                md = _table_to_markdown(shape.table)
                if md:
                    blocks.append(ParsedBlock(text=md, page=page_num, section=section, block_type="table"))
                continue
            if not shape.has_text_frame:
                continue
            for paragraph in shape.text_frame.paragraphs:
                parts = []
                for run in paragraph.runs:
                    if _run_is_hidden(run):
                        if run.text.strip():
                            hidden_total += 1
                        continue
                    parts.append(run.text)
                text = "".join(parts).strip()
                if text:
                    blocks.append(ParsedBlock(text=text, page=page_num, section=section, block_type="paragraph"))

        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            notes = slide.notes_slide.notes_text_frame.text.strip()
            blocks.append(ParsedBlock(text=f"[Speaker notes] {notes}", page=page_num, section=section, block_type="paragraph"))

    if hidden_total:
        warnings.append(f"removed {hidden_total} hidden/invisible text run(s) before indexing")

    return ParsedDocument(blocks=blocks, page_count=len(prs.slides), used_ocr=False, warnings=warnings)
