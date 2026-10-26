"""Identifikatorlar: uuid v7 (TZ 8.1). Python 3.13 da `uuid.uuid7` yo'q (3.14 da paydo bo'ladi)."""

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 uuid v7: 48 bit unix ms + tasodifiy; vaqt bo'yicha tartiblangan (indeks uchun qulay)."""
    millis = time.time_ns() // 1_000_000
    raw = bytearray(millis.to_bytes(6, "big") + os.urandom(10))
    raw[6] = (raw[6] & 0x0F) | 0x70  # versiya 7
    raw[8] = (raw[8] & 0x3F) | 0x80  # variant RFC 4122
    return uuid.UUID(bytes=bytes(raw))
