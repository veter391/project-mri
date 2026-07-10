"""Structured JSON logging.

Every log record includes:
- timestamp (ISO-8601 UTC)
- level
- logger name
- message
- request_id (when in a request context)
- any extra fields passed via `logger.info(..., extra={...})`

Default format: JSON (machine-readable). For local dev, set
`MRI_LOG_FORMAT=text` for human-friendly output.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from typing import Any

# Context variable for request ID propagation
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(rid: str | None = None) -> str:
    rid = rid or uuid.uuid4().hex[:12]
    _request_id_var.set(rid)
    return rid


def get_request_id() -> str | None:
    return _request_id_var.get()


def clear_request_id() -> None:
    _request_id_var.set(None)


class JsonFormatter(logging.Formatter):
    """JSON log formatter for production."""

    # Standard LogRecord attributes we DON'T want to dump as "extra"
    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        # Add extra fields
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith("_"):
                try:
                    json.dumps(v)  # test serializable
                    payload[k] = v
                except (TypeError, ValueError):
                    payload[k] = repr(v)
        # Exception info
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-friendly formatter for local dev."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        rid = get_request_id()
        prefix = f"[{rid}] " if rid else ""
        return f"{time.strftime('%H:%M:%S', time.gmtime(record.created))} [{record.levelname}] {prefix}{record.name}: {record.getMessage()}"


_LOG_FORMAT = os.environ.get("MRI_LOG_FORMAT", "json").lower()
_LOG_LEVEL = os.environ.get("MRI_LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """Configure the root logger. Idempotent."""
    root = logging.getLogger()
    # Remove existing handlers (uvicorn installs its own — replace them too)
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if _LOG_FORMAT == "text":
        handler.setFormatter(TextFormatter())
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

    # Quiet down noisy libraries
    logging.getLogger("multipart.multipart").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)