"""Log formatters for production (e.g. JSON lines on stdout)."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone


class JsonLinesFormatter(logging.Formatter):
    """One JSON object per line for Loki, Datadog, Cloud Logging, etc."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "lineno": record.lineno,
        }
        if record.exc_info:
            payload["exc_info"] = "".join(traceback.format_exception(*record.exc_info)).strip()
        return json.dumps(payload, default=str)
