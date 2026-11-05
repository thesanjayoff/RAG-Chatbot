"""Plain text and Markdown parsing. Markdown headings (#...######) become
section boundaries; blank-line-separated runs become paragraphs; fenced
code blocks are kept intact instead of being split mid-block."""
from __future__ import annotations

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError


def _read_text(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not read file: {exc}") from exc
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            return text.replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file as text")


def parse_markdown(path: str) -> ParsedDocument:
    text = _read_text(path)
    lines = text.splitlines()
    blocks: list[ParsedBlock] = []
    current_section: str | None = None
    buffer: list[str] = []
    in_code = False
    code_buffer: list[str] = []

    def flush_paragraph():
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(ParsedBlock(text=joined, page=None, section=current_section, block_type="paragraph"))
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                code_buffer.append(line)
                code_text = "\n".join(code_buffer)
                blocks.append(ParsedBlock(text=code_text, page=None, section=current_section, block_type="paragraph"))
                code_buffer = []
                in_code = False
            else:
                flush_paragraph()
                in_code = True
                code_buffer = [line]
            continue
        if in_code:
            code_buffer.append(line)
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped[level:].strip()
            current_section = heading_text or current_section
            blocks.append(
                ParsedBlock(text=heading_text, page=None, section=current_section, block_type="heading", heading_level=level)
            )
        elif stripped.startswith(("- ", "* ", "+ ")) or (stripped[:2].isdigit() and ". " in stripped[:4]):
            flush_paragraph()
            blocks.append(ParsedBlock(text=stripped, page=None, section=current_section, block_type="list_item"))
        elif stripped == "":
            flush_paragraph()
        else:
            buffer.append(line)

    flush_paragraph()
    return ParsedDocument(blocks=blocks, page_count=0)


def parse_txt(path: str) -> ParsedDocument:
    text = _read_text(path)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    blocks = [ParsedBlock(text=p, page=None, section=None, block_type="paragraph") for p in paragraphs]
    return ParsedDocument(blocks=blocks, page_count=0)
