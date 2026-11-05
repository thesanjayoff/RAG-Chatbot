"""Background folder watching. Polling (rather than OS filesystem-event
hooks) was chosen deliberately: it works identically across Windows/macOS/
Linux, survives the app being closed and reopened without missing
changes, and a personal document collection changes rarely enough that a
periodic scan has no noticeable downside.
"""
from __future__ import annotations

import logging
import threading

from app.db import SessionLocal

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30


class FolderWatcherService:
    def __init__(self, interval: int = DEFAULT_INTERVAL_SECONDS):
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="folder-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        from app.ingestion.sync import sync_watched_folder
        from app.models import WatchedFolder

        while not self._stop.is_set():
            try:
                db = SessionLocal()
                try:
                    folders = db.query(WatchedFolder).all()
                    for folder in folders:
                        try:
                            stats = sync_watched_folder(db, folder)
                            if any(stats.values()):
                                logger.info("watched folder %s: %s", folder.path, stats)
                        except Exception as exc:  # noqa: BLE001
                            logger.error("error syncing watched folder %s: %s", folder.path, exc)
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                logger.error("folder watcher loop error: %s", exc)
            self._stop.wait(self.interval)


watcher_service = FolderWatcherService()
