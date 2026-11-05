"""Heuristic detection of likely secrets or personal data inside a
document's extracted text, so the user can be warned before indexing
(and before that content potentially surfaces in an answer)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS Secret Key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?")),
    ("Generic API key", re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token)\b\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Anthropic-style key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("Password assignment", re.compile(r"(?i)\bpassword\b\s*[=:]\s*['\"]?\S{6,}['\"]?")),
    ("Social Security Number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("Credit card number", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("Email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]

# Email addresses are common and often benign in business documents; they
# are reported separately as "personal data" rather than "secret" severity.
_PII_LABELS = {"Email address", "Social Security Number", "Credit card number"}


@dataclass
class SecretFinding:
    label: str
    count: int
    severity: str  # "secret" | "pii"
    sample_masked: str


@dataclass
class ScanReport:
    findings: list[SecretFinding] = field(default_factory=list)

    @property
    def has_secrets(self) -> bool:
        return any(f.severity == "secret" for f in self.findings)

    @property
    def has_pii(self) -> bool:
        return any(f.severity == "pii" for f in self.findings)

    def summary(self) -> str:
        if not self.findings:
            return ""
        parts = [f"{f.label} x{f.count}" for f in self.findings]
        return "; ".join(parts)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def scan_text(text: str) -> ScanReport:
    report = ScanReport()
    for label, pattern in _PATTERNS:
        matches = pattern.findall(text) if pattern.groups else pattern.findall(text)
        found = list(pattern.finditer(text))
        if not found:
            continue
        severity = "pii" if label in _PII_LABELS else "secret"
        sample = _mask(found[0].group(0))
        report.findings.append(SecretFinding(label=label, count=len(found), severity=severity, sample_masked=sample))
    return report


def mask_secrets(text: str) -> str:
    """Return a copy of text with likely secrets replaced by a placeholder.
    Used only when the user opts in to masking before indexing."""
    masked = text
    for label, pattern in _PATTERNS:
        if label in _PII_LABELS:
            continue
        masked = pattern.sub(f"[REDACTED:{label}]", masked)
    return masked
