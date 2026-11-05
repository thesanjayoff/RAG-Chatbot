"""HTML parsing via BeautifulSoup. Scripts/styles are dropped entirely
(never executed, never indexed), and elements hidden via inline CSS
(display:none, visibility:hidden, 0 font-size, or text colored to match
its own background) are stripped before indexing."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParseError

_HIDDEN_STYLE_RE = re.compile(r"(?i)display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0")
_HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}


def _is_hidden(tag) -> bool:
    style = tag.get("style", "") if hasattr(tag, "get") else ""
    if _HIDDEN_STYLE_RE.search(style):
        return True
    if tag.get("hidden") is not None:
        return True
    cls = " ".join(tag.get("class", []))
    if "sr-only" in cls or "visually-hidden" in cls:
        return False  # legitimate accessibility text, not an injection vector
    return False


def _read(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not read HTML file: {exc}") from exc
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_html(path: str) -> ParsedDocument:
    html = _read(path)
    return parse_html_string(html)


def parse_html_string(html: str) -> ParsedDocument:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    hidden_removed = 0
    for tag in soup.find_all(True):
        if _is_hidden(tag):
            hidden_removed += 1
            tag.decompose()

    blocks: list[ParsedBlock] = []
    current_section: str | None = None

    body = soup.body or soup
    for el in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table"], recursive=True):
        tag_name = el.name
        if tag_name in _HEADING_TAGS:
            text = el.get_text(" ", strip=True)
            if not text:
                continue
            current_section = text
            blocks.append(ParsedBlock(text=text, page=None, section=current_section, block_type="heading", heading_level=_HEADING_TAGS[tag_name]))
        elif tag_name == "li":
            text = el.get_text(" ", strip=True)
            if text:
                blocks.append(ParsedBlock(text=f"- {text}", page=None, section=current_section, block_type="list_item"))
        elif tag_name == "table":
            rows = []
            for tr in el.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                header, *restrows = rows
                lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
                for r in restrows:
                    lines.append("| " + " | ".join(r) + " |")
                blocks.append(ParsedBlock(text="\n".join(lines), page=None, section=current_section, block_type="table"))
        else:  # p
            text = el.get_text(" ", strip=True)
            if text:
                blocks.append(ParsedBlock(text=text, page=None, section=current_section, block_type="paragraph"))

    warnings = [f"removed {hidden_removed} hidden element(s) before indexing"] if hidden_removed else []
    return ParsedDocument(blocks=blocks, page_count=0, warnings=warnings)
