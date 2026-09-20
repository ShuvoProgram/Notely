"""Structured JSON logging. Never log secrets or raw provider content."""

from __future__ import annotations

import contextvars
import logging
import sys

from pythonjsonlogger.json import JsonFormatter

# Set by the request middleware so every log line in a request carries the same ids.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)

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


class ContextFilter(logging.Filter):
    """Attach the current request id / user id (never the session token) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if "request_id" not in record.__dict__:
            record.request_id = request_id_var.get()
        if "user_id" not in record.__dict__:
            record.user_id = user_id_var.get()
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
    handler.addFilter(ContextFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
