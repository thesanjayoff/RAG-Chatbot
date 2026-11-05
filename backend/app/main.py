from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def _warm_up_ocr() -> None:
    """Downloads/loads the OCR model weights once, in the main process
    (which has network access), so the parsing sandbox -- which has
    outbound sockets disabled -- never needs to fetch them itself."""
    if not settings.ocr_enabled:
        return
    try:
        from PIL import Image

        from app.ingestion.ocr import ocr_image

        blank = Image.new("RGB", (64, 64), color="white")
        ocr_image(blank)
        logger.info("OCR model warm-up complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR warm-up failed (scanned-document OCR may not work until this succeeds): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db import init_db
    from app.ingestion.watcher import watcher_service
    from app.retrieval import bm25_index

    init_db()

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        bm25_index.rebuild_index(db)
    finally:
        db.close()

    threading.Thread(target=_warm_up_ocr, daemon=True).start()
    watcher_service.start()

    logger.info("Personal RAG Chatbot backend ready on http://%s:%s (fully_local_mode=%s)", settings.host, settings.port, settings.fully_local_mode)
    yield

    watcher_service.stop()
    from app.ingestion.sandbox import shutdown as shutdown_sandbox

    shutdown_sandbox()


app = FastAPI(title="Personal RAG Chatbot", lifespan=lifespan)

# This app is designed to run entirely on localhost. CORS is opened only
# to the local Vite dev server origins so the browser-based UI can call
# the API during development; in production the frontend is served by
# this same process (see the StaticFiles mount below), so no cross-origin
# requests are needed at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import analysis, chat, conversations, documents, settings_api, watched_folders  # noqa: E402

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(analysis.router)
app.include_router(watched_folders.router)
app.include_router(settings_api.router)


@app.get("/api/ping")
def ping():
    return {"status": "ok"}


_frontend_dist = settings.data_dir.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
