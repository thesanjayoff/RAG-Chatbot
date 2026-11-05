"""Logging setup that redacts likely secrets from every log line before it
hits a handler, so a document containing an API key never leaks it into
the server's log file via an error message or debug trace."""
from __future__ import annotations

import logging

from app.security.secrets_scan import mask_secrets


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = mask_secrets(str(record.getMessage()))
            record.args = ()
        except Exception:  # noqa: BLE001
            pass
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    redact = RedactSecretsFilter()
    # Filters attached to a logger only run for records logged directly on
    # that logger, not on propagation -- so to redact everything (messages
    # logged by any module's logger) the filter must live on the root
    # logger's handler(s), which every propagated record passes through.
    for handler in logging.getLogger().handlers:
        handler.addFilter(redact)
