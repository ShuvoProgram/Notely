"""Structured JSON logging. Never log secrets or raw provider content."""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

_REDACT_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
}


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key.lower() in _REDACT_KEYS:
                record.__dict__[key] = "[redacted]"
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s", rename_fields={"levelname": "level"}
        )
    )
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
