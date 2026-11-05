from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.ingestion.sync import register_watched_folder, sync_watched_folder
from app.schemas import WatchedFolderCreate

router = APIRouter(prefix="/api/watched-folders", tags=["watched-folders"])


def _to_dict(f) -> dict:
    return {
        "id": f.id,
        "path": f.path,
        "recursive": f.recursive,
        "last_scanned_at": f.last_scanned_at.isoformat() if f.last_scanned_at else None,
    }


def _scan_job(folder_id: str) -> None:
    from app.models import WatchedFolder

    db = SessionLocal()
    try:
        folder = db.get(WatchedFolder, folder_id)
        if folder is not None:
            sync_watched_folder(db, folder)
    finally:
        db.close()


@router.get("")
def list_watched_folders(db: Session = Depends(get_db)):
    from app.models import WatchedFolder

    return [_to_dict(f) for f in db.query(WatchedFolder).all()]


@router.post("")
def add_watched_folder(body: WatchedFolderCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        folder = register_watched_folder(db, body.path, body.recursive)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_scan_job, folder.id)
    return _to_dict(folder)


@router.post("/{folder_id}/scan")
def scan_now(folder_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.models import WatchedFolder

    folder = db.get(WatchedFolder, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="watched folder not found")
    background_tasks.add_task(_scan_job, folder_id)
    return {"status": "scanning"}


@router.delete("/{folder_id}")
def remove_watched_folder(folder_id: str, db: Session = Depends(get_db)):
    from app.models import Document, WatchedFolder

    folder = db.get(WatchedFolder, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="watched folder not found")
    from app.ingestion.sync import delete_document

    doc_ids = [d.id for d in db.query(Document).filter_by(watched_folder_id=folder_id).all()]
    for doc_id in doc_ids:
        delete_document(db, doc_id)
    db.delete(folder)
    db.commit()
    return {"status": "deleted"}
