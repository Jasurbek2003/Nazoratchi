"""Paket va namunalarni tekshirish (TZ 7.5.2, 16.2.4)."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .catalog import (
    ALLOWED_LABELS,
    MAX_LABEL_VALUE_LEN,
    NAME_RE,
    value_in_range,
)


class BatchError(Exception):
    """Butun paket yaroqsiz (sxema xatosi) -> 400."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class Sample:
    name: str
    labels: dict[str, str]
    t_ms: int
    value: float


def parse_batch(payload: object) -> tuple[str, int, datetime, list[Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise BatchError("body", "JSON obyekt bo'lishi kerak.")
    batch_id = payload.get("batch_id")
    if not isinstance(batch_id, str) or not (1 <= len(batch_id) <= 64):
        raise BatchError("batch_id", "batch_id (1-64 belgili matn) majburiy.")
    seq = payload.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise BatchError("seq", "seq manfiy bo'lmagan butun son bo'lishi kerak.")
    sent_raw = payload.get("sent_at")
    if not isinstance(sent_raw, str):
        raise BatchError("sent_at", "sent_at (ISO-8601) majburiy.")
    try:
        sent_at = datetime.fromisoformat(sent_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BatchError("sent_at", "sent_at ISO-8601 formatida bo'lishi kerak.") from exc
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)
    samples = payload.get("samples", [])
    if not isinstance(samples, list):
        raise BatchError("samples", "samples ro'yxat bo'lishi kerak.")
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        raise BatchError("facts", "facts obyekt bo'lishi kerak.")
    return batch_id, seq, sent_at, samples, facts


def parse_sample(raw: object) -> Sample | None:
    """Yaroqli namunani qaytaradi, yaroqsiz bo'lsa None (namuna rad etiladi, paket emas)."""
    if not isinstance(raw, dict):
        return None
    name, t_ms, value = raw.get("n"), raw.get("t"), raw.get("v")
    if not isinstance(name, str) or not NAME_RE.match(name):
        return None
    if not isinstance(t_ms, int) or isinstance(t_ms, bool) or t_ms < 0:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    value = float(value)
    if not math.isfinite(value) or not value_in_range(name, value):
        return None
    labels_raw = raw.get("l", {})
    if not isinstance(labels_raw, dict):
        return None
    labels: dict[str, str] = {}
    for key, val in labels_raw.items():
        if key not in ALLOWED_LABELS or not isinstance(val, str) or len(val) > MAX_LABEL_VALUE_LEN:
            return None
        labels[key] = val
    return Sample(name=name, labels=labels, t_ms=t_ms, value=value)
