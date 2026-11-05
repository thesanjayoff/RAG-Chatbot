from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.ingestion.pipeline import ingest_file
from app.ingestion.sync import delete_document, register_upload, register_url
from app.schemas import UrlIngestRequest
from app.security.file_validation import ValidationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

SCRATCH_DIR = settings.data_dir / "uploads_tmp"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def document_to_dict(doc) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
        "error_message": doc.error_message,
        "progress": doc.progress,
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
        "used_ocr": doc.used_ocr,
        "secrets_flag": doc.secrets_flag,
        "secrets_summary": doc.secrets_summary,
        "injection_flag": doc.injection_flag,
        "injection_summary": doc.injection_summary,
        "source_type": doc.source_type,
        "source_path": doc.source_path,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "tags": [t.name for t in doc.tags],
    }


def _run_ingest_job(document_id: str) -> None:
    db = SessionLocal()
    try:
        ingest_file(db, document_id)
    except Exception:  # noqa: BLE001
        logger.exception("background ingestion crashed for document %s", document_id)
    finally:
        db.close()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    tmp_path = SCRATCH_DIR / f"{uuid.uuid4().hex}_{Path(file.filename or 'upload').name}"
    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        with tmp_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValidationError(f"file exceeds {settings.max_upload_mb}MB limit")
                out.write(chunk)
    except ValidationError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=exc.reason) from exc
    finally:
        await file.close()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    result = register_upload(db, file.filename or "upload", tmp_path, tag_list)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if "duplicate_of" in result:
        return {"status": "duplicate", **result}

    background_tasks.add_task(_run_ingest_job, result["document_id"])
    return {"status": "queued", "document_id": result["document_id"]}


@router.post("/url")
def ingest_url(req: UrlIngestRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    result = register_url(db, req.url, req.tags)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if "duplicate_of" in result:
        return {"status": "duplicate", **result}
    background_tasks.add_task(_run_ingest_job, result["document_id"])
    return {"status": "queued", "document_id": result["document_id"]}


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    from app.models import Document

    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [document_to_dict(d) for d in docs]


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    from app.models import Document

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document_to_dict(doc)


@router.delete("/{document_id}")
def remove_document(document_id: str, db: Session = Depends(get_db)):
    ok = delete_document(db, document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="document not found")
    return {"status": "deleted"}


@router.post("/{document_id}/reindex")
def reindex_document(document_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.models import Document

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    doc.status = "pending"
    doc.progress = 0.0
    db.commit()
    background_tasks.add_task(_run_ingest_job, document_id)
    return {"status": "queued"}


@router.put("/{document_id}/tags")
def set_tags(document_id: str, tags: list[str], db: Session = Depends(get_db)):
    from app.models import Document, Tag

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    doc.tags = []
    for name in tags:
        name = name.strip()
        if not name:
            continue
        tag = db.query(Tag).filter_by(name=name).first() or Tag(name=name)
        doc.tags.append(tag)
    db.commit()
    return document_to_dict(doc)


@router.get("/{document_id}/file")
def get_document_file(document_id: str, db: Session = Depends(get_db)):
    from app.models import Document

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    path = Path(doc.stored_path).resolve()
    if not path.exists() or not path.is_relative_to(settings.documents_dir.resolve()):
        raise HTTPException(status_code=404, detail="file not found")
    media_types = {
        "pdf": "application/pdf",
        "image": "application/octet-stream",
    }
    return FileResponse(path, media_type=media_types.get(doc.file_type, "application/octet-stream"), filename=doc.filename)


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str, db: Session = Depends(get_db)):
    from app.models import Chunk, Document

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    rows = db.query(Chunk).filter_by(document_id=document_id).order_by(Chunk.chunk_index).all()
    return [
        {
            "id": c.id,
            "chunk_index": c.chunk_index,
            "text": c.text,
            "section": c.section,
            "page_start": c.page_start,
            "page_end": c.page_end,
        }
        for c in rows
    ]


@router.get("/tags/all")
def list_tags(db: Session = Depends(get_db)):
    from app.models import Tag

    return [t.name for t in db.query(Tag).order_by(Tag.name).all()]
