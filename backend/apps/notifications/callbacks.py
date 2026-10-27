"""Telegram tugma ma'lumoti (`callback_data`) imzosi (TZ 9.12, TH-11): `ack:<incident_id>:<sig>`,
`snz:<incident_id>:<daqiqa>:<sig>`. Imzo HMAC-SHA256 (SECRET_KEY dan olingan alohida kalit), 12 hex belgi:
`callback_data` Telegram'da ≤ 64 bayt."""

import hashlib
import hmac

from django.conf import settings

SIG_LEN = 12


def _key() -> bytes:
    return hashlib.sha256(b"nazoratchi-telegram-callback|" + settings.SECRET_KEY.encode()).digest()


def sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()[:SIG_LEN]


def make(action: str, incident_id: str, *extra: str) -> str:
    payload = ":".join([action, incident_id, *extra])
    return f"{payload}:{sign(payload)}"


def parse(data: str) -> tuple[str, str, list[str]] | None:
    """(amal, incident_id, qo'shimcha) yoki imzo noto'g'ri bo'lsa None."""
    payload, _, sig = data.rpartition(":")
    parts = payload.split(":")
    if len(parts) < 2 or not hmac.compare_digest(sign(payload), sig):
        return None
    return parts[0], parts[1], parts[2:]
