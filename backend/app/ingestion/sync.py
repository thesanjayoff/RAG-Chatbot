"""Higher-level ingestion operations: registering an upload (with
validation + duplicate detection), deleting a document everywhere it's
stored, and syncing a watched folder (new/changed/deleted files)."""
from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.pipeline import ingest_file
from app.retrieval import bm25_index, vectorstore
from app.security.file_validation import ValidationError, validate_upload

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".md", ".markdown", ".txt", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
}


def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_by_hash(db, file_hash: str):
    from app.models import Document

    return db.query(Document).filter(Document.file_hash == file_hash, Document.status != "error").first()


def register_upload(db: Session, filename: str, tmp_path: Path, tags: list[str] | None = None) -> dict:
    from app.models import Document, Tag

    try:
        result = validate_upload(tmp_path, filename)
    except ValidationError as exc:
        tmp_path.unlink(missing_ok=True)
        return {"error": exc.reason}

    file_hash = compute_file_hash(tmp_path)
    existing = _find_by_hash(db, file_hash)
    if existing is not None:
        tmp_path.unlink(missing_ok=True)
        return {"duplicate_of": existing.id, "filename": existing.filename}

    doc_id = uuid.uuid4().hex
    doc_dir = settings.documents_dir / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name  # strips any directory components -> no path traversal
    dest = doc_dir / safe_name
    shutil.move(str(tmp_path), str(dest))

    document = Document(
        id=doc_id,
        filename=safe_name,
        stored_path=str(dest),
        file_type=result.file_type,
        file_hash=file_hash,
        size_bytes=result.size_bytes,
        source_type="upload",
        status="pending",
    )
    if tags:
        for name in tags:
            name = name.strip()
            if not name:
                continue
            tag = db.query(Tag).filter_by(name=name).first() or Tag(name=name)
            document.tags.append(tag)
    db.add(document)
    db.commit()
    return {"document_id": document.id}


def register_url(db: Session, url: str, tags: list[str] | None = None) -> dict:
    from app.ingestion.parsers.web_parser import fetch_and_parse_url
    from app.ingestion.parsers.base import ParseError
    from app.models import Document, Tag

    if not settings.network_allowed():
        return {"error": "fully-local mode is on: fetching a web page requires network access"}

    try:
        # Fetch happens here, in the main process (network allowed); only
        # the parsing of the already-downloaded HTML runs in the sandbox.
        import httpx

        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            resp = client.get(url, headers={"User-Agent": "personal-rag-chatbot/1.0"})
            resp.raise_for_status()
            html_bytes = resp.content
    except Exception as exc:  # noqa: BLE001
        return {"error": f"failed to fetch URL: {exc}"}

    file_hash = hashlib.sha256(html_bytes).hexdigest()
    existing = _find_by_hash(db, file_hash)
    if existing is not None:
        return {"duplicate_of": existing.id, "filename": existing.filename}

    doc_id = uuid.uuid4().hex
    doc_dir = settings.documents_dir / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    dest = doc_dir / "page.html"
    dest.write_bytes(html_bytes)

    title = url
    document = Document(
        id=doc_id,
        filename=title,
        stored_path=str(dest),
        file_type="html",
        file_hash=file_hash,
        size_bytes=len(html_bytes),
        source_type="url",
        source_path=url,
        status="pending",
    )
    if tags:
        for name in tags:
            name = name.strip()
            if not name:
                continue
            tag = db.query(Tag).filter_by(name=name).first() or Tag(name=name)
            document.tags.append(tag)
    db.add(document)
    db.commit()
    return {"document_id": document.id}


def delete_document(db: Session, document_id: str) -> bool:
    from app.models import Document

    document = db.get(Document, document_id)
    if document is None:
        return False

    vectorstore.delete_by_document(document_id)
    doc_dir = Path(document.stored_path).parent
    if document.source_type == "upload" and doc_dir.exists() and doc_dir.is_relative_to(settings.documents_dir):
        shutil.rmtree(doc_dir, ignore_errors=True)

    db.delete(document)
    db.commit()
    bm25_index.rebuild_index(db)
    return True


def register_watched_folder(db: Session, path: str, recursive: bool = True):
    from app.models import WatchedFolder

    folder_path = Path(path).resolve()
    if not folder_path.exists() or not folder_path.is_dir():
        raise ValueError(f"not a directory: {path}")
    existing = db.query(WatchedFolder).filter_by(path=str(folder_path)).first()
    if existing:
        return existing
    folder = WatchedFolder(path=str(folder_path), recursive=recursive)
    db.add(folder)
    db.commit()
    return folder


def sync_watched_folder(db: Session, folder) -> dict:
    """One pass over a watched folder: ingest new/changed files, remove
    documents whose source file is gone. Safe to call repeatedly (e.g.
    from a filesystem-event handler or a periodic/manual rescan)."""
    from app.models import Document

    folder_path = Path(folder.path)
    pattern = "**/*" if folder.recursive else "*"
    on_disk: dict[str, Path] = {}
    if folder_path.exists():
        for p in folder_path.glob(pattern):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                on_disk[str(p.resolve())] = p

    existing_docs = db.query(Document).filter_by(watched_folder_id=folder.id).all()
    existing_by_path = {d.source_path: d for d in existing_docs}

    added, updated, removed, skipped = 0, 0, 0, 0

    for path_str in set(existing_by_path) - set(on_disk):
        delete_document(db, existing_by_path[path_str].id)
        removed += 1

    for path_str, p in on_disk.items():
        try:
            file_hash = compute_file_hash(p)
        except OSError:
            continue
        doc = existing_by_path.get(path_str)
        if doc is not None:
            if doc.file_hash == file_hash:
                skipped += 1
                continue
            delete_document(db, doc.id)
            updated += 1
        else:
            dup = _find_by_hash(db, file_hash)
            if dup is not None:
                skipped += 1
                continue
            added += 1

        try:
            result = validate_upload(p, p.name)
        except ValidationError as exc:
            logger.warning("skipping %s: %s", p, exc.reason)
            continue

        doc_id = uuid.uuid4().hex
        doc_dir = settings.documents_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        dest = doc_dir / p.name
        shutil.copy2(p, dest)

        document = Document(
            id=doc_id,
            filename=p.name,
            stored_path=str(dest),
            file_type=result.file_type,
            file_hash=file_hash,
            size_bytes=result.size_bytes,
            source_type="watched_folder",
            source_path=path_str,
            watched_folder_id=folder.id,
            status="pending",
        )
        db.add(document)
        db.commit()
        ingest_file(db, document.id)

    from datetime import datetime, timezone

    folder.last_scanned_at = datetime.now(timezone.utc)
    db.commit()

    return {"added": added, "updated": updated, "removed": removed, "skipped": skipped}
