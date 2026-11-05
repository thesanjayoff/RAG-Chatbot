"""Entry point: `python run.py`. Binds to localhost by default (see
app/config.py) since this app holds personal documents."""
import os
import sys

# EasyOCR's model-download progress bar prints Unicode block characters
# (e.g. U+2588) straight to stdout; Windows' default console code page
# (cp1252) can't encode them and raises UnicodeEncodeError, which crashes
# the download mid-way and leaves OCR unusable. Force UTF-8 here (and
# propagate it to the spawned sandbox worker processes via the
# environment) before anything else can print.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
