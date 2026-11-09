"""Structured application logging with defensive secret redaction."""
import json
import logging
import re
from datetime import datetime, timezone


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        message = re.sub(r"(?i)postgres(?:ql)?(?:\+\w+)?://[^\s]+", "[DATABASE_URL_REDACTED]", message)
        message = re.sub(r"(?i)(password|api_key|token|authorization)\s*[=:]\s*\S+", r"\1=[REDACTED]", message)
        # Exception strings can contain SQL parameters and DSNs; log type only.
        return json.dumps({
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": message,
            "request_id": getattr(record, "request_id", None),
        }, ensure_ascii=False)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("adventure_camp")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(SafeFormatter())
        logger.addHandler(handler)
