"""Defenses against two different threats that both arrive as "just text
inside a document":

1. Hidden text (white-on-white runs, 0pt/near-0pt fonts, zero-width
   Unicode characters, HTML comments) that a document author used to hide
   content from a human reader but that a naive text extractor would still
   feed to the LLM as if the user had seen it.
2. Prompt injection: text engineered to look like instructions ("ignore
   previous instructions", "you are now...") aimed at hijacking the model
   once that text is pulled into the prompt as retrieved context.

Neither is foolproof -- this is defense in depth, not a guarantee -- but
both are cheap, local, and meaningfully raise the bar.
"""
from __future__ import annotations

import re
import uuid

import bleach

ZERO_WIDTH_CHARS = "​‌‍﻿⁠"
_ZERO_WIDTH_RE = re.compile(f"[{ZERO_WIDTH_CHARS}]")

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_ALLOWED_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "h1", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "td", "th", "a", "code", "pre", "blockquote", "span"]
_ALLOWED_ATTRS = {"a": ["href"]}

# Phrases commonly used in prompt-injection attempts. Used only to *flag*
# a document for the user's attention -- the actual defense is that the
# LLM is instructed (see app/llm/prompts.py) to treat all retrieved text
# as inert data, never as instructions, regardless of what it contains.
_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |any )?(previous|prior|above) instructions"),
    re.compile(r"(?i)disregard (all |any )?(previous|prior|above)"),
    re.compile(r"(?i)you are now (a|an|in) "),
    re.compile(r"(?i)\bsystem\s*:\s*"),
    re.compile(r"(?i)new instructions?\s*:"),
    re.compile(r"(?i)reveal (your|the) (system )?prompt"),
    re.compile(r"(?i)act as (if|though) you"),
    re.compile(r"(?i)do not (tell|inform|mention) the user"),
    re.compile(r"(?i)\bjailbreak\b"),
    re.compile(r"(?i)print (your|the) (api|secret) key"),
]


def strip_zero_width(text: str) -> tuple[str, int]:
    count = len(_ZERO_WIDTH_RE.findall(text))
    return _ZERO_WIDTH_RE.sub("", text), count


def strip_html_comments(html: str) -> tuple[str, int]:
    count = len(_HTML_COMMENT_RE.findall(html))
    return _HTML_COMMENT_RE.sub(" ", html), count


def sanitize_html(html: str) -> str:
    """Make document-derived HTML safe to ever render in the UI."""
    cleaned, _ = strip_html_comments(html)
    return bleach.clean(cleaned, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def detect_injection_phrases(text: str) -> list[str]:
    hits = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def clean_extracted_text(text: str) -> tuple[str, dict]:
    """Run all text-level hygiene steps on freshly-parsed document text.
    Returns (cleaned_text, flags) where flags records what was found so
    the ingestion pipeline can surface a warning to the user."""
    cleaned, zw_count = strip_zero_width(text)
    injection_hits = detect_injection_phrases(cleaned)
    flags = {
        "zero_width_chars_removed": zw_count,
        "injection_phrases_found": injection_hits,
    }
    return cleaned, flags


def build_delimited_context(chunks: list[dict]) -> tuple[str, str]:
    """Wrap retrieved chunks in a per-request random delimiter so the LLM
    can be told, unambiguously, where untrusted document data starts and
    ends. The nonce is regenerated every request so a document can't
    predict and spoof the delimiter string in advance."""
    nonce = uuid.uuid4().hex[:12]
    tag = f"DOCUMENT_DATA_{nonce}"
    parts = []
    for c in chunks:
        header = f"[source_id={c['source_id']} file={c['filename']} page={c.get('page', '?')}]"
        parts.append(f"<{tag}>\n{header}\n{c['text']}\n</{tag}>")
    return "\n\n".join(parts), tag
