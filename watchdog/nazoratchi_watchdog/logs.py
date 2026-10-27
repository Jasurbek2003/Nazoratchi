"""JSON loglar (ts/level/component/msg) va maxfiy qiymatlarni maskalash (TZ 14.9)."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

_SECRETS: set[str] = set()
_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")
COMPONENT = "watchdog"


def register_secret(value: str) -> None:
    """Qiymatni keyingi barcha loglarda va xato matnlarida `***` ga almashtirish uchun eslab qoladi."""
    if value:
        _SECRETS.add(value)


def clear_secrets() -> None:
    _SECRETS.clear()


def mask(text: str) -> str:
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(secret, "***")
    return _TOKEN_RE.sub("bot***", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "component": COMPONENT,
            "msg": mask(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = mask(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("nazoratchi_watchdog")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
