"""Strukturalangan JSON log va maxfiy qiymatlarni maskalash (NFR-MNT-005, NFR-SEC-008)."""

import json
import logging
import re
from datetime import UTC, datetime

# TZ 14.9: token, secret, password, authorization qiymatlari logga tushmasligi kerak.
# `Authorization: Bearer <token>` da "Bearer" dan keyingi qiymat ham yopiladi.
_SECRET_RE = re.compile(
    r"(?i)((?:token|secret|password|authorization)\S*\s*[=:]\s*(?:(?:bearer|basic)\s+)?)\S+"
)


def mask_secrets(text: str) -> str:
    return _SECRET_RE.sub(r"\1***", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "component": record.name,
            "msg": mask_secrets(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)
