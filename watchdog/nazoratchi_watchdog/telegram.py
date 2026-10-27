"""Telegram sendMessage (stdlib urllib). Token hech qachon log yoki xatoda ko'rinmaydi."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from nazoratchi_watchdog.logs import mask

log = logging.getLogger("nazoratchi_watchdog.telegram")

RETRY_DELAYS_S: tuple[float, ...] = (1, 2, 4, 8, 16)


class TelegramNotifier:
    def __init__(
        self,
        api: str,
        token: str,
        chat_id: str,
        *,
        timeout_s: float = 10.0,
        delays: tuple[float, ...] = RETRY_DELAYS_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = f"{api.rstrip('/')}/bot{token}/sendMessage"
        self._token = token
        self._chat_id = chat_id
        self._timeout = timeout_s
        self._delays = delays
        self._sleep = sleep

    def _safe(self, text: str) -> str:
        return mask(text.replace(self._token, "***"))

    def _attempt(self, text: str) -> tuple[bool, bool, str]:
        """(muvaffaqiyat, qayta_urinish_mumkin, xato_matni)."""
        body = json.dumps(
            {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - sxema config'da http/https ga tekshirilgan
            self._url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                payload = json.loads(resp.read(65536).decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as exc:
            retry = exc.code == 429 or exc.code >= 500
            return False, retry, f"Telegram HTTP {exc.code}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return False, True, f"tarmoq xatosi: {self._safe(str(exc))}"
        except ValueError:
            return False, True, "Telegram javobi JSON emas"
        if isinstance(payload, dict) and payload.get("ok") is True:
            return True, False, ""
        return False, False, "Telegram ok=false qaytardi"

    def send(self, text: str) -> bool:
        """Yuboradi; vaqtincha xatolarda 1,2,4,8,16 s kutib qayta uriniladi. True — yuborildi."""
        error = ""
        for attempt in range(len(self._delays) + 1):
            ok, retry, error = self._attempt(text)
            if ok:
                return True
            log.warning("Telegram'ga yuborilmadi (urinish %d): %s", attempt + 1, error)
            if not retry or attempt >= len(self._delays):
                break
            self._sleep(self._delays[attempt])
        log.error("Xabar yuborilmadi, keyingi tsiklda yana uriniladi: %s", error)
        return False
