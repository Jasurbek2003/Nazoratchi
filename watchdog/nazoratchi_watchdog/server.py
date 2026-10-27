"""HTTP qabul qiluvchi: GET|POST /ping/<id>, GET /healthz."""

from __future__ import annotations

import hmac
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from nazoratchi_watchdog.monitor import Monitor

log = logging.getLogger("nazoratchi_watchdog.server")

MAX_PATH = 2048
MAX_BODY = 1024
MAX_REASON = 100
MAX_PARAM = 200
PING_PREFIX = "/ping/"


def clean_reason(raw: str) -> str:
    """Faqat bosma ASCII (0x20-0x7E) qoladi, qolgani '?' bo'ladi; 100 belgigacha kesiladi.

    HTML ekranlash (Telegram) xabar yig'ilganda alohida bajariladi.
    """
    raw = raw[:MAX_REASON]
    return "".join(ch if " " <= ch <= "~" else "?" for ch in raw).strip()


def parse_ping_query(query: str) -> tuple[str, str]:
    params = parse_qs(query, max_num_fields=10)
    status = params.get("s", ["ok"])[0][:MAX_PARAM]
    reason = params.get("reason", [""])[0][:MAX_PARAM]
    return ("degraded" if status == "degraded" else "ok"), clean_reason(reason)


def id_matches(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


class WatchdogServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], monitor: Monitor, watchdog_id: str) -> None:
        self.monitor = monitor
        self.watchdog_id = watchdog_id
        super().__init__(addr, _Handler)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # ulanish yopiladi: o'qilmagan tana muammo tug'dirmaydi
    timeout = 10
    server_version = "nazoratchi-watchdog"
    sys_version = ""

    @property
    def _srv(self) -> WatchdogServer:
        return cast(WatchdogServer, self.server)

    def _reply(self, code: int, body: str = "") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _handle(self) -> None:
        if len(self.path) > MAX_PATH:
            self._reply(414, "uzun manzil")
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._reply(413, "tana katta")
            return
        if length > 0:
            self.rfile.read(length)  # tashlab yuboriladi

        parts = urlsplit(self.path)
        if parts.path == "/healthz" and self.command == "GET":
            self._reply(200, "ok")
            return
        if parts.path.startswith(PING_PREFIX):
            candidate = parts.path[len(PING_PREFIX) :]
            if id_matches(candidate, self._srv.watchdog_id):
                status, reason = parse_ping_query(parts.query)
                self._srv.monitor.record_ping(status, reason)
                self._reply(200, "ok")
                return
            # Manzil logga yozilmaydi: unda maxfiy id bo'lishi mumkin.
            log.warning("Noto'g'ri id bilan ping urinishi: %s", self.client_address[0])
        self._reply(404, "topilmadi")

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def log_message(self, format: str, *args: Any) -> None:
        return  # standart so'rov logi o'chirilgan (manzilda maxfiy id bor)
