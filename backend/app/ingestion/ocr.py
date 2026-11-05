"""Shared OCR engine. Uses EasyOCR (pure-Python + torch, bundles its own
models) instead of requiring a system Tesseract install, which is a common
source of setup friction on Windows."""
from __future__ import annotations

import logging
import threading

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_reader = None
_lock = threading.Lock()


def _get_reader():
    global _reader
    if _reader is None:
        with _lock:
            if _reader is None:
                import easyocr

                langs = [s.strip() for s in settings.ocr_languages.split(",") if s.strip()] or ["en"]
                logger.info("Loading EasyOCR reader for languages=%s (first run downloads model weights)", langs)
                _reader = easyocr.Reader(langs, gpu=False)
    return _reader


def ocr_image(pil_image) -> str:
    if not settings.ocr_enabled:
        return ""
    reader = _get_reader()
    arr = np.array(pil_image.convert("RGB"))
    results = reader.readtext(arr, detail=0, paragraph=True)
    return "\n".join(results)
