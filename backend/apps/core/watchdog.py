"""Watchdog'ga ping (FR-SYS-002): core har 60 soniyada S-01 dagi watchdog'ga "tirikman" deydi. 5 daqiqa kelmasa
watchdog mustaqil Telegram bot orqali xabar beradi. URL maxfiy identifikatorni o'z ichiga oladi: hech qachon
logga yoki xato matniga tushmaydi."""

import logging
import time
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from .health import watchdog_status

logger = logging.getLogger(__name__)

PING_EVERY_S = 60
TIMEOUT_S = 5.0


def ping(status: str, reason: str = "", url: str | None = None) -> bool:
    """Bitta ping. Qaytadi: muvaffaqiyatlimi. Sozlanmagan bo'lsa (`WATCHDOG_URL` bo'sh) — hech narsa qilmaydi (True)."""
    url = url if url is not None else settings.WATCHDOG_URL
    if not url:
        return True
    params = {"s": status}
    if reason:
        params["reason"] = reason[:100]
    host = urlsplit(url).netloc  # logga faqat host (yo'l maxfiy id ni o'z ichiga oladi)
    try:
        response = httpx.get(url, params=params, timeout=TIMEOUT_S, follow_redirects=False)
    except httpx.HTTPError as exc:
        logger.warning("watchdog ping yuborilmadi (%s): %s", host, type(exc).__name__)
        return False
    if response.status_code != 200:
        logger.warning("watchdog ping rad etildi (%s): HTTP %s", host, response.status_code)
        return False
    return True


class Pinger:
    """Dvigatel siklida chaqiriladi; `PING_EVERY_S` dan tez-tez yubormaydi."""

    def __init__(self) -> None:
        self._last = 0.0

    def maybe_ping(self, force: bool = False) -> bool | None:
        """None — hali erta yoki sozlanmagan; aks holda ping natijasi."""
        if not settings.WATCHDOG_URL:
            return None
        now = time.monotonic()
        if not force and now - self._last < PING_EVERY_S:
            return None
        self._last = now
        status, reason = watchdog_status()
        return ping(status, reason)
