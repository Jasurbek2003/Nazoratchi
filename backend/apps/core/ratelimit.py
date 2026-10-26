"""Qat'iy oynali tezlik chegarasi (NFR-SEC-007). Kesh bilan ishlaydi; kesh yo'q bo'lsa o'tkazadi."""

import logging
import time
from dataclasses import dataclass

from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0


def hit(scope: str, ident: str, limit: int, window_s: int) -> Decision:
    """`ident` uchun `window_s` soniyalik oynada `limit` tadan ortiq so'rovga ruxsat bermaydi."""
    now = int(time.time())
    bucket = now // window_s
    key = f"rl:{scope}:{ident}:{bucket}"
    try:
        cache.add(key, 0, window_s + 1)
        count = int(cache.incr(key))
    except Exception:  # kesh nosoz bo'lsa so'rov to'xtamasligi kerak (fail-open)
        logger.warning("tezlik chegarasi: kesh xatosi (%s)", scope, exc_info=True)
        return Decision(True)
    if count > limit:
        return Decision(False, retry_after=(bucket + 1) * window_s - now)
    return Decision(True)
