"""Upload validation: every document is treated as hostile input until
proven otherwise. We check real file content (not the extension the
uploader claims), enforce size limits, and guard against zip/decompression
bombs hiding inside Office documents before we ever hand bytes to a parser.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import filetype

from app.config import settings

# Magic-byte signatures we trust, mapped to our internal file_type labels.
# Anything not recognized by `filetype` (true for plain-text formats like
# md/txt/csv/html) is sniffed separately below.
_BINARY_KIND_MAP = {
    "pdf": "pdf",
    "docx": "docx",
    "pptx": "pptx",
    "xlsx": "xlsx",
    "doc": "doc",  # legacy binary formats are rejected, see SUPPORTED set
    "ppt": "ppt",
    "xls": "xls",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "tif": "image",
    "tiff": "image",
    "bmp": "image",
    "webp": "image",
    "zip": "zip",
}

SUPPORTED_TYPES = {"pdf", "docx", "pptx", "xlsx", "csv", "md", "txt", "html", "image"}

# Office Open XML formats are zip containers; zip bombs disguise a huge
# payload behind a tiny compressed size. Reject anything whose claimed
# uncompressed size is absurd relative to the compressed size, or whose
# total uncompressed size is unreasonable outright.
MAX_ZIP_RATIO = 120
MAX_ZIP_UNCOMPRESSED_MB = 500
MAX_ZIP_ENTRIES = 10_000


class ValidationError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class ValidationResult:
    file_type: str
    size_bytes: int


def _sniff_text_type(filename: str, head: bytes) -> str | None:
    suffix = Path(filename).suffix.lower()
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if suffix in (".md", ".markdown"):
        return "md"
    if suffix == ".csv":
        return "csv"
    if suffix in (".htm", ".html"):
        return "html"
    if suffix == ".txt":
        return "txt"
    # Unknown extension but valid utf-8 text: best-effort sniff by content.
    stripped = head.lstrip()
    if stripped.startswith(b"<!DOCTYPE html") or stripped.startswith(b"<html"):
        return "html"
    return "txt"


def check_zip_bomb(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValidationError(f"archive has too many entries ({len(infos)})")
            total_uncompressed = 0
            for info in infos:
                total_uncompressed += info.file_size
                if info.compress_size > 0:
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > MAX_ZIP_RATIO and info.file_size > 10_000_000:
                        raise ValidationError(
                            f"archive entry '{info.filename}' has suspicious compression ratio ({ratio:.0f}x)"
                        )
            if total_uncompressed > MAX_ZIP_UNCOMPRESSED_MB * 1024 * 1024:
                raise ValidationError(
                    f"archive would decompress to {total_uncompressed / 1e6:.0f}MB (limit "
                    f"{MAX_ZIP_UNCOMPRESSED_MB}MB)"
                )
    except zipfile.BadZipFile as exc:
        raise ValidationError("file claims to be a zip-based format but is not a valid archive") from exc


def validate_upload(path: Path, filename: str) -> ValidationResult:
    """Validate a file already written to disk. Raises ValidationError on
    any policy violation. Returns the detected (trusted) file type."""
    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise ValidationError("file is empty")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValidationError(f"file is {size_bytes / 1e6:.1f}MB, limit is {settings.max_upload_mb}MB")

    with path.open("rb") as fh:
        head = fh.read(4096)

    kind = filetype.guess(str(path))
    detected: str | None = None
    if kind is not None:
        detected = _BINARY_KIND_MAP.get(kind.extension)
        if detected == "zip":
            # Office formats are zips with a particular internal layout;
            # distinguish by extension of the *claimed* filename, but only
            # trust that after the zip itself passes the bomb check.
            suffix = Path(filename).suffix.lower().lstrip(".")
            if suffix in ("docx", "pptx", "xlsx"):
                detected = suffix
            else:
                detected = None  # unknown zip contents: refuse
    if detected is None:
        detected = _sniff_text_type(filename, head)

    if detected is None or detected not in SUPPORTED_TYPES:
        raise ValidationError(
            f"file content was not recognized as a supported type (got kind={kind.mime if kind else 'unknown'})"
        )

    if detected in ("docx", "pptx", "xlsx"):
        check_zip_bomb(path)

    return ValidationResult(file_type=detected, size_bytes=size_bytes)


def safe_join(base_dir: Path, *parts: str) -> Path:
    """Join path parts under base_dir, refusing any traversal outside it."""
    candidate = (base_dir / Path(*parts)).resolve()
    base_resolved = base_dir.resolve()
    if base_resolved not in candidate.parents and candidate != base_resolved:
        raise ValidationError("path traversal detected")
    return candidate
