"""Redis tushsa ham ishlashda davom etadigan kesh (TZ NFR-REL-004, T-C-02).

Tezlik chegarasi va throttling kabi yordamchi ma'lumotlar uchun: Redis javob bermasa, kesh "bo'sh" deb
hisoblanadi (so'rov o'tkaziladi), 500 bermaydi. Asosiy ma'lumot Redis'da saqlanmaydi.
"""

import logging
from typing import Any

from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_MISSING = object()


class FailOpenRedisCache(RedisCache):
    def _guard(self, name: str, default: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(super(), name)(*args, **kwargs)
        except (RedisError, OSError):
            logger.warning("kesh: Redis mavjud emas (%s); so'rov cheklovsiz o'tkazildi", name)
            return default

    def get(self, key: Any, default: Any = None, version: Any = None) -> Any:
        return self._guard("get", default, key, default, version)

    def set(self, key: Any, value: Any, timeout: Any = _MISSING, version: Any = None) -> Any:
        if timeout is _MISSING:
            return self._guard("set", None, key, value, version=version)
        return self._guard("set", None, key, value, timeout, version)

    def add(self, key: Any, value: Any, timeout: Any = _MISSING, version: Any = None) -> bool:
        if timeout is _MISSING:
            return bool(self._guard("add", True, key, value, version=version))
        return bool(self._guard("add", True, key, value, timeout, version))

    def incr(self, key: Any, delta: int = 1, version: Any = None) -> int:
        return int(self._guard("incr", 0, key, delta, version))

    def delete(self, key: Any, version: Any = None) -> bool:
        return bool(self._guard("delete", False, key, version))
