from __future__ import annotations

import os
import zipfile

import pytest

from app.security.file_validation import ValidationError, check_zip_bomb, safe_join, validate_upload
from app.security.secrets_scan import mask_secrets, scan_text


def test_content_based_detection_overrides_a_spoofed_pdf_extension(tmp_path):
    """A plain-text file renamed to end in .pdf must be identified by its
    real content, not handed to the PDF parser just because of its name."""
    p = tmp_path / "totally_a_report.pdf"
    p.write_text("This is actually just plain text, not a PDF.", encoding="utf-8")
    result = validate_upload(p, p.name)
    assert result.file_type == "txt"


def test_random_binary_disguised_as_docx_is_rejected(tmp_path):
    p = tmp_path / "fake.docx"
    p.write_bytes(os.urandom(4096))
    with pytest.raises(ValidationError):
        validate_upload(p, p.name)


def test_empty_file_is_rejected(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_bytes(b"")
    with pytest.raises(ValidationError):
        validate_upload(p, p.name)


def test_oversized_file_is_rejected(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    p = tmp_path / "big.txt"
    p.write_bytes(b"x" * (2 * 1024 * 1024))
    with pytest.raises(ValidationError):
        validate_upload(p, p.name)


def test_zip_bomb_is_rejected_by_compression_ratio(tmp_path):
    p = tmp_path / "bomb.zip"
    payload = b"\x00" * 11_000_000  # 11MB of zeros compresses to almost nothing
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("huge.bin", payload)
    with pytest.raises(ValidationError):
        check_zip_bomb(p)


def test_normal_docx_passes_zip_bomb_check(tmp_path):
    from docx import Document as DocxDocument

    p = tmp_path / "normal.docx"
    d = DocxDocument()
    d.add_paragraph("Just a normal short document.")
    d.save(str(p))
    check_zip_bomb(p)  # should not raise


def test_safe_join_rejects_path_traversal(tmp_path):
    base = tmp_path / "documents"
    base.mkdir()
    with pytest.raises(ValidationError):
        safe_join(base, "..", "..", "etc", "passwd")


def test_safe_join_allows_normal_relative_path(tmp_path):
    base = tmp_path / "documents"
    base.mkdir()
    result = safe_join(base, "sub", "file.txt")
    assert result == (base / "sub" / "file.txt").resolve()


def test_secrets_scan_detects_aws_key_and_private_key_block():
    text = """
    Here is some config:
    aws_access_key_id = AKIAIOSFODNN7EXAMPLE
    -----BEGIN RSA PRIVATE KEY-----
    MIIBOgIBAAJBAK...
    -----END RSA PRIVATE KEY-----
    """
    report = scan_text(text)
    labels = {f.label for f in report.findings}
    assert "AWS Access Key ID" in labels
    assert "Private key block" in labels
    assert report.has_secrets is True


def test_secrets_scan_flags_email_as_pii_not_secret():
    report = scan_text("Contact jane.doe@example.com for details.")
    labels = {f.label: f.severity for f in report.findings}
    assert labels.get("Email address") == "pii"
    assert report.has_pii is True


def test_mask_secrets_redacts_aws_key_but_leaves_benign_text():
    text = "key=AKIAIOSFODNN7EXAMPLE and the weather is nice"
    masked = mask_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in masked
    assert "the weather is nice" in masked
