"""Process isolation for document parsing. Every untrusted file is parsed
in a dedicated worker process (so a hostile or malformed file can crash or
hang only that worker, never the API server) and that worker has outbound
sockets disabled at import time, so even a parser bug or a malicious
library call can't phone home.

This is defense in depth, not a full OS sandbox (no seccomp/network
namespace) -- see the README's security section for the honest scope of
what this does and doesn't guarantee. OCR model weights are pre-downloaded
by the main process at startup (see app.ingestion.ocr warm-up in main.py)
specifically so the sandboxed worker never needs network access, even on
first use.
"""
from __future__ import annotations

import socket
from concurrent.futures import ProcessPoolExecutor

_executor: ProcessPoolExecutor | None = None
DEFAULT_TIMEOUT_SECONDS = 180


def _block_network() -> None:
    def _blocked(*_args, **_kwargs):
        raise RuntimeError("network access is disabled inside the document-parsing sandbox")

    socket.socket.connect = _blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked  # type: ignore[method-assign]


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=1, initializer=_block_network)
    return _executor


def run_sandboxed(fn, *args, timeout: int = DEFAULT_TIMEOUT_SECONDS, **kwargs):
    future = _get_executor().submit(fn, *args, **kwargs)
    return future.result(timeout=timeout)


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
