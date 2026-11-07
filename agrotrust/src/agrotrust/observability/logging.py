"""Structured JSON logging (spec section 42).

No OpenTelemetry/Sentry here - both need network egress this sandbox doesn't have. In a real
deployment, swap this for an OTel exporter; the log *shape* (structured, one JSON object per
line, request_id correlation) is designed to translate directly into OTel log records later.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": round(time.time(), 3), "level": record.levelname, "logger": record.name,
                  "message": record.getMessage(), "request_id": _request_id.get()}
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:16]
    _request_id.set(rid)
    return rid


def log(logger: logging.Logger, level: int, message: str, **fields) -> None:
    logger.log(level, message, extra={"fields": fields})
