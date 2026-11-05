"""Single entry point the sandbox worker process calls. Must stay a plain
module-level function (not a closure/lambda) so it can be pickled by
reference across the process boundary."""
from __future__ import annotations

from app.ingestion.parsers.base import ParsedDocument, ParseError


def parse_document(file_type: str, path: str, ocr_enabled: bool) -> ParsedDocument:
    ocr_fn = None
    if ocr_enabled:
        from app.ingestion.ocr import ocr_image

        ocr_fn = ocr_image

    if file_type == "pdf":
        from app.ingestion.parsers.pdf_parser import parse_pdf

        return parse_pdf(path, ocr_fn=ocr_fn)
    if file_type == "docx":
        from app.ingestion.parsers.docx_parser import parse_docx

        return parse_docx(path)
    if file_type == "pptx":
        from app.ingestion.parsers.pptx_parser import parse_pptx

        return parse_pptx(path)
    if file_type == "xlsx":
        from app.ingestion.parsers.xlsx_parser import parse_xlsx

        return parse_xlsx(path)
    if file_type == "csv":
        from app.ingestion.parsers.xlsx_parser import parse_csv

        return parse_csv(path)
    if file_type == "md":
        from app.ingestion.parsers.text_parser import parse_markdown

        return parse_markdown(path)
    if file_type == "txt":
        from app.ingestion.parsers.text_parser import parse_txt

        return parse_txt(path)
    if file_type == "html":
        from app.ingestion.parsers.html_parser import parse_html

        return parse_html(path)
    if file_type == "image":
        from app.ingestion.parsers.image_parser import parse_image

        return parse_image(path, ocr_fn=ocr_fn)
    raise ParseError(f"no parser registered for file type {file_type!r}")


def parse_html_text(html: str) -> ParsedDocument:
    from app.ingestion.parsers.html_parser import parse_html_string

    return parse_html_string(html)
