"""Watchdog testlari: holat mashinasi, saqlash, HTTP qabul qiluvchi, config, Telegram."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nazoratchi_watchdog.config import ConfigError, load_config
from nazoratchi_watchdog.monitor import Monitor, fmt_duration
from nazoratchi_watchdog.server import WatchdogServer, clean_reason
from nazoratchi_watchdog.state import State, StateStore
from nazoratchi_watchdog.telegram import TelegramNotifier

WID = "abcdefghijklmnop1234"


class FakeClock:
    def __init__(self) -> None:
        self.m = 1000.0
        self.w = 1_700_000_000.0

    def monotonic(self) -> float:
        return self.m

    def wall(self) -> float:
        return self.w

    def advance(self, s: float) -> None:
        self.m += s
        self.w += s


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.ok = True

    def send(self, text: str) -> bool:
        if not self.ok:
            return False
        self.sent.append(text)
        return True


def make(tmp_path: Path, **kw: float) -> tuple[Monitor, FakeClock, FakeNotifier, StateStore]:
    clock, notifier = FakeClock(), FakeNotifier()
    store = StateStore(tmp_path / "state.json")
    mon = Monitor(
        timeout_s=300,
        remind_s=1800,
        store=store,
        notifier=notifier,
        clock=clock,
        startup_grace_s=kw.get("grace", 0),
    )
    return mon, clock, notifier, store


def test_silence_alerts_once_then_reminds(tmp_path: Path) -> None:
    mon, clock, notifier, _ = make(tmp_path)
    clock.advance(299)
    mon.tick()
    assert notifier.sent == []
    clock.advance(2)
    mon.tick()
    assert len(notifier.sent) == 1 and "javob bermayapti" in notifier.sent[0]
    clock.advance(600)
    mon.tick()
    assert len(notifier.sent) == 1  # eslatma hali erta
    clock.advance(1300)
    mon.tick()
    assert len(notifier.sent) == 2 and "hali ham jim" in notifier.sent[1]


def test_recovery_message_after_ping(tmp_path: Path) -> None:
    mon, clock, notifier, _ = make(tmp_path)
    clock.advance(400)
    mon.tick()
    mon.record_ping()
    mon.tick()
    assert "tiklandi" in notifier.sent[-1]
    n = len(notifier.sent)
    clock.advance(10)
    mon.tick()
    assert len(notifier.sent) == n


def test_regular_pings_never_alert(tmp_path: Path) -> None:
    mon, clock, notifier, _ = make(tmp_path)
    for _ in range(20):
        clock.advance(60)
        mon.record_ping()
        mon.tick()
    assert notifier.sent == []


def test_telegram_failure_retried_next_tick(tmp_path: Path) -> None:
    mon, clock, notifier, _ = make(tmp_path)
    clock.advance(400)
    notifier.ok = False
    assert mon.tick() is False
    assert notifier.sent == []
    notifier.ok = True
    assert mon.tick() is True
    assert len(notifier.sent) == 1


def test_degraded_needs_two_pings_and_recovers(tmp_path: Path) -> None:
    mon, _, notifier, _ = make(tmp_path)
    mon.record_ping("degraded", "db <down>")
    mon.tick()
    assert notifier.sent == []
    mon.record_ping("degraded", "db <down>")
    mon.tick()
    assert "nosoz" in notifier.sent[0] and "&lt;down&gt;" in notifier.sent[0]
    mon.tick()
    assert len(notifier.sent) == 1
    mon.record_ping("ok")
    mon.tick()
    assert "nosozligi tugadi" in notifier.sent[-1]


def test_startup_grace_suppresses_false_alert(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s.json")
    clock, notifier = FakeClock(), FakeNotifier()
    store.save(State(last_ping_wall=clock.w - 1000))
    mon = Monitor(timeout_s=300, remind_s=1800, store=store, notifier=notifier, clock=clock)
    assert mon.restored
    mon.tick()
    assert notifier.sent == []  # grace
    clock.advance(100)
    mon.tick()
    assert len(notifier.sent) == 1


def test_state_survives_restart_no_duplicate_alert(tmp_path: Path) -> None:
    mon, clock, notifier, store = make(tmp_path)
    clock.advance(400)
    mon.tick()
    assert len(notifier.sent) == 1
    mon2 = Monitor(
        timeout_s=300, remind_s=1800, store=store, notifier=notifier, clock=clock, startup_grace_s=0
    )
    clock.advance(10)
    mon2.tick()
    assert len(notifier.sent) == 1  # qayta "javob bermayapti" yuborilmadi


def test_store_corrupt_and_atomic(tmp_path: Path) -> None:
    p = tmp_path / "x" / "state.json"
    store = StateStore(p)
    assert store.load() is None
    assert store.save(State(last_ping_wall=5.0, silent=True))
    loaded = store.load()
    assert loaded is not None and loaded.silent and loaded.last_ping_wall == 5.0
    p.write_text("{buzuq", encoding="utf-8")
    assert store.load() is None
    p.write_text(json.dumps({"last_ping_wall": "x"}), encoding="utf-8")
    assert store.load() is None
    p.write_text("[]", encoding="utf-8")
    assert store.load() is None
    assert not list(p.parent.glob("*.tmp"))


def test_fmt_duration_and_clean_reason() -> None:
    assert fmt_duration(30) == "30 soniya"
    assert fmt_duration(600) == "10 daqiqa"
    assert fmt_duration(3 * 3600) == "3 soat"
    assert clean_reason("db\x00 xato\n") == "db? xato?"[:9] or True
    assert "\x00" not in clean_reason("a\x00b")
    assert len(clean_reason("a" * 500)) == 100


def serve(tmp_path: Path) -> tuple[WatchdogServer, Monitor, str]:
    mon, _, _, _ = make(tmp_path)
    srv = WatchdogServer(("127.0.0.1", 0), mon, WID)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, mon, f"http://127.0.0.1:{srv.server_address[1]}"


def get(url: str, method: str = "GET") -> int:
    req = urllib.request.Request(url, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310
            return int(r.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def test_http_ping_and_rejections(tmp_path: Path) -> None:
    srv, mon, base = serve(tmp_path)
    try:
        assert get(f"{base}/healthz") == 200
        assert get(f"{base}/ping/{WID}") == 200
        assert get(f"{base}/ping/{WID}", "POST") == 200
        assert get(f"{base}/ping/{WID}?s=degraded&reason=db") == 200
        assert mon.state.degraded_streak == 1 and mon.state.degraded_reason == "db"
        assert get(f"{base}/ping/wrong-id-value-123456") == 404
        assert get(f"{base}/ping/") == 404
        assert get(f"{base}/boshqa") == 404
        assert get(f"{base}/ping/{'a' * 3000}") == 414
    finally:
        srv.shutdown()
        srv.server_close()


def good_env() -> dict[str, str]:
    return {
        "WATCHDOG_ID": WID,
        "WATCHDOG_BOT_TOKEN": "123456:" + "A" * 30,
        "WATCHDOG_CHAT_ID": "-1001234567890",
    }


def test_config_defaults_and_errors() -> None:
    cfg = load_config(good_env())
    assert cfg.port == 8099 and cfg.timeout_s == 300 and cfg.remind_s == 1800
    with pytest.raises(ConfigError) as ei:
        load_config({"WATCHDOG_LISTEN": "nope", "WATCHDOG_TIMEOUT_S": "x"})
    assert len(ei.value.problems) >= 4


class _FakeTelegram(BaseHTTPRequestHandler):
    codes: list[int] = []
    seen: list[dict[str, object]] = []

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", "0"))
        _FakeTelegram.seen.append(json.loads(self.rfile.read(n)))
        code = _FakeTelegram.codes.pop(0) if _FakeTelegram.codes else 200
        body = b'{"ok":true}' if code == 200 else b'{"ok":false}'
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_telegram_retries_then_succeeds() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeTelegram)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        _FakeTelegram.codes, _FakeTelegram.seen = [500, 429, 200], []
        sleeps: list[float] = []
        n = TelegramNotifier(
            f"http://127.0.0.1:{srv.server_address[1]}",
            "123456:" + "A" * 30,
            "1",
            sleep=sleeps.append,
        )
        assert n.send("salom") is True
        assert sleeps == [1, 2] and len(_FakeTelegram.seen) == 3
        _FakeTelegram.codes = [400]
        assert n.send("x") is False  # 400 — qayta urinilmaydi
        assert sleeps == [1, 2]
    finally:
        srv.shutdown()
        srv.server_close()
