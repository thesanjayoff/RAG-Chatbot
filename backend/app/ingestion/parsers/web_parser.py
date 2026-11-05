"""Web page ingestion. Disabled outright in fully-local mode since fetching
a URL is, by definition, an outbound network call."""
from __future__ import annotations

import httpx

from app.config import settings
from app.ingestion.parsers.base import ParsedDocument, ParseError
from app.ingestion.parsers.html_parser import parse_html_string

MAX_RESPONSE_BYTES = 25 * 1024 * 1024


def fetch_and_parse_url(url: str) -> ParsedDocument:
    if not settings.network_allowed():
        raise ParseError("fully-local mode is on: fetching a web page requires network access")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ParseError("only http(s) URLs are supported")

    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            with client.stream("GET", url, headers={"User-Agent": "personal-rag-chatbot/1.0"}) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    raise ParseError(f"URL did not return HTML (content-type={content_type!r})")
                chunks = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise ParseError("page exceeded maximum allowed size")
                    chunks.append(chunk)
                raw = b"".join(chunks)
    except httpx.HTTPError as exc:
        raise ParseError(f"failed to fetch URL: {exc}") from exc

    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        html = raw.decode("latin-1", errors="replace")

    parsed = parse_html_string(html)
    parsed.warnings.append(f"fetched from {url}")
    return parsed
