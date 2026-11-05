"""Excel (.xlsx) and CSV parsing. Spreadsheets are chunked into row-batches
per sheet up front (rather than left as one giant block) so the later
structure-aware chunker doesn't have to split an arbitrary wall of text."""
from __future__ import annotations

import csv
from pathlib import Path

import openpyxl

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError

ROWS_PER_BLOCK = 40


def _rows_to_markdown(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _stringify(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def parse_xlsx(path: str) -> ParsedDocument:
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not open XLSX: {exc}") from exc

    blocks: list[ParsedBlock] = []
    for sheet in wb.worksheets:
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            continue
        header = [_stringify(v) or f"col{i+1}" for i, v in enumerate(header_row)]
        blocks.append(ParsedBlock(text=f"Sheet: {sheet.title}", page=None, section=sheet.title, block_type="heading"))

        batch: list[list[str]] = []
        for row in rows_iter:
            if row is None or all(v is None for v in row):
                continue
            batch.append([_stringify(v) for v in row])
            if len(batch) >= ROWS_PER_BLOCK:
                blocks.append(
                    ParsedBlock(text=_rows_to_markdown(header, batch), page=None, section=sheet.title, block_type="table")
                )
                batch = []
        if batch:
            blocks.append(
                ParsedBlock(text=_rows_to_markdown(header, batch), page=None, section=sheet.title, block_type="table")
            )

    wb.close()
    return ParsedDocument(blocks=blocks, page_count=len(wb.sheetnames) if hasattr(wb, "sheetnames") else 0)


def parse_csv(path: str) -> ParsedDocument:
    name = Path(path).stem
    try:
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.reader(fh)
            rows = list(reader)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not read CSV: {exc}") from exc

    if not rows:
        return ParsedDocument(blocks=[], page_count=0)

    header = [h.strip() or f"col{i+1}" for i, h in enumerate(rows[0])]
    blocks = [ParsedBlock(text=f"Table: {name}", page=None, section=name, block_type="heading")]
    batch: list[list[str]] = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        batch.append([cell.strip() for cell in row])
        if len(batch) >= ROWS_PER_BLOCK:
            blocks.append(ParsedBlock(text=_rows_to_markdown(header, batch), page=None, section=name, block_type="table"))
            batch = []
    if batch:
        blocks.append(ParsedBlock(text=_rows_to_markdown(header, batch), page=None, section=name, block_type="table"))

    return ParsedDocument(blocks=blocks, page_count=1)
