"""JSON logging with request context and a strict field allowlist."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Serialize only explicitly approved operational fields."""

    _field_names = (
        "event",
        "request_id",
        "tenant_id",
        "project_id",
        "method",
        "path",
        "status_code",
        "latency_ms",
        "error_code",
        "exception_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "request_id": request_id_context.get(),
        }
        for field_name in self._field_names:
            value = getattr(record, field_name, None)
            if value is not None:
                entry[field_name] = (
                    str(value) if field_name in {"tenant_id", "project_id"} else value
                )
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level_name: str) -> logging.Logger:
    """Configure one JSON stream handler for application events."""

    logger = logging.getLogger("guardrail_mini")
    logger.setLevel(level_name.upper())
    logger.propagate = False
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger
