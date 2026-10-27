import argparse
import gzip
import json
import math
import os
import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from proto_agent.collectors import Collector, host_facts
from proto_agent.main import BUFFER_MAX_AGE_S, Agent, resolve_token, run
from proto_agent.sender import (
    Batch,
    EnrollError,
    Sender,
    SendResult,
    build_payload,
    enroll,
)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
ALLOWED_LABELS = {"mount", "device", "fstype", "iface"}


# ---------- kollektorlar ----------
def test_collector_returns_valid_samples() -> None:
    samples = Collector().collect()
    names = {s["n"] for s in samples}
    assert {"cpu_busy_percent", "mem_used_percent", "load1", "uptime_seconds"} <= names
    for s in samples:
        assert NAME_RE.match(s["n"]), s
        assert math.isfinite(s["v"]), s
        assert isinstance(s["t"], int) and s["t"] > 0
        assert set(s["l"]) <= ALLOWED_LABELS
        if s["n"].endswith("_percent"):
            assert 0.0 <= s["v"] <= 100.0, s


def test_net_rates_are_computed_from_counter_difference() -> None:
    counters = {"eth0": (1000, 500), "lo": (1, 1)}
    now = [100.0]
    collector = Collector(net_counters=lambda: counters, clock=lambda: now[0])
    first = [s for s in collector.collect() if s["n"].startswith("net_")]
    assert first == []  # birinchi o'lchovda tezlik yo'q

    counters["eth0"] = (3000, 1500)
    now[0] = 110.0
    rates = {s["n"]: s["v"] for s in collector.collect() if s["n"].startswith("net_")}
    assert rates == {"net_rx_bytes_per_sec": 200.0, "net_tx_bytes_per_sec": 100.0}  # lo yashirin


def test_net_counter_reset_never_gives_negative_rate() -> None:
    counters = {"eth0": (10_000, 10_000)}
    now = [0.0]
    collector = Collector(net_counters=lambda: counters, clock=lambda: now[0])
    collector.collect()
    counters["eth0"] = (50, 50)  # reboot/qayta boshlash
    now[0] = 15.0
    rates = [s["v"] for s in collector.collect() if s["n"].startswith("net_")]
    assert rates == [0.0, 0.0]


def test_host_facts_have_expected_keys() -> None:
    facts = host_facts()
    assert {"hostname", "os", "arch", "cpu_count", "mem_total_bytes"} <= set(facts)


# ---------- sender (haqiqiy HTTP server bilan) ----------
class _Stub(BaseHTTPRequestHandler):
    queued: list[tuple[int, dict[str, str], bytes]] = []
    received: list[dict[str, Any]] = []
    headers_seen: list[dict[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        type(self).received.append(json.loads(raw))
        type(self).headers_seen.append(dict(self.headers.items()))
        status, headers, body = type(self).queued.pop(0)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def stub() -> Iterator[tuple[type[_Stub], str]]:
    _Stub.queued, _Stub.received, _Stub.headers_seen = [], [], []
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield _Stub, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _batch() -> Batch:
    return Batch("b-1", 1, [{"n": "load1", "t": 1, "v": 0.5, "l": {}}], {"hostname": "x"})


def test_sender_posts_gzip_json_with_token(stub: tuple[type[_Stub], str]) -> None:
    handler, url = stub
    handler.queued = [(200, {}, b'{"ok": true, "accepted": 1}')]
    result = Sender(url, "agt_test").send(_batch())
    assert result.outcome == "ok" and result.response["accepted"] == 1
    payload = handler.received[0]
    assert payload["batch_id"] == "b-1" and payload["facts"] == {"hostname": "x"}
    assert payload["sent_at"].endswith("Z")
    seen = handler.headers_seen[0]
    assert seen["Authorization"] == "Bearer agt_test" and seen["Content-Encoding"] == "gzip"


@pytest.mark.parametrize(
    ("status", "headers", "outcome", "retry_after"),
    [
        (400, {}, "drop", None),
        (413, {}, "drop", None),
        (401, {}, "retry", 300.0),
        (429, {"Retry-After": "7"}, "retry", 7.0),
        (429, {}, "retry", 30.0),
        (500, {}, "retry", None),
        (503, {}, "retry", None),
    ],
)
def test_sender_error_classification(
    stub: tuple[type[_Stub], str],
    status: int,
    headers: dict[str, str],
    outcome: str,
    retry_after: float | None,
) -> None:
    handler, url = stub
    handler.queued = [(status, headers, b"{}")]
    result = Sender(url, "t").send(_batch())
    assert (result.outcome, result.retry_after) == (outcome, retry_after)


def test_sender_network_error_is_retry() -> None:
    result = Sender("http://127.0.0.1:9", "t", timeout=1.0).send(_batch())  # port yopiq
    assert result.outcome == "retry" and result.status is None


def test_payload_without_facts_omits_key() -> None:
    batch = Batch("b", 1, [])
    assert "facts" not in build_payload(batch)


# ---------- agent: bufer va qayta urinish ----------
class FakeCollector(Collector):
    def __init__(self) -> None:  # psutil ni ishga tushirmaydi
        pass

    def collect(self, now_ms: int | None = None) -> list[dict[str, Any]]:
        return [{"n": "load1", "t": 1, "v": 1.0, "l": {}}]


class FakeSender(Sender):
    def __init__(self, results: list[SendResult]) -> None:
        self.results = results
        self.sent: list[str] = []

    def send(self, batch: Batch) -> SendResult:
        self.sent.append(batch.batch_id)
        return self.results.pop(0) if self.results else SendResult("ok", 200)


def make_agent(results: list[SendResult]) -> tuple[Agent, FakeSender, list[float], list[str]]:
    now = [1000.0]
    logs: list[str] = []
    sender = FakeSender(results)
    agent = Agent(FakeCollector(), sender, clock=lambda: now[0], log=logs.append)
    return agent, sender, now, logs


def test_failed_batches_are_buffered_and_sent_in_order_after_recovery() -> None:
    agent, sender, now, _ = make_agent([SendResult("retry", 500)])
    agent.tick()  # 1-paket: xato
    assert len(agent.queue) == 1
    now[0] += 5  # backoff (1 s) o'tdi
    agent.tick()  # 2-paket: navbatda 1-paket oldin yuboriladi
    assert len(agent.queue) == 0
    assert [b.split("-")[-1] for b in sender.sent] == ["1", "1", "2"]


def test_no_retry_before_backoff_expires() -> None:
    agent, sender, now, _ = make_agent([SendResult("retry", 500)])
    agent.tick()
    calls = len(sender.sent)
    now[0] += 0.1  # backoff (~1 s) hali o'tmagan
    agent.tick()
    assert len(sender.sent) == calls and len(agent.queue) == 2


def test_backoff_grows_and_is_capped() -> None:
    agent, _, now, _ = make_agent([SendResult("retry", 500)] * 12)
    delays = []
    for _ in range(8):
        agent.tick()
        delays.append(agent.next_attempt - now[0])
        now[0] = agent.next_attempt + 0.001
    assert delays[0] < delays[2] < delays[4]
    assert max(delays) <= 30 * 1.1 + 1e-9


def test_retry_after_is_respected() -> None:
    agent, _, now, _ = make_agent([SendResult("retry", 429, retry_after=7.0)])
    agent.tick()
    assert agent.next_attempt - now[0] == pytest.approx(7.0)


def test_rejected_batch_is_dropped_not_retried_forever() -> None:
    agent, sender, _, logs = make_agent([SendResult("drop", 400, detail="HTTP 400")])
    agent.tick()
    assert len(agent.queue) == 0 and len(sender.sent) == 1
    assert any("rad etildi" in line for line in logs)


def test_buffer_drops_batches_older_than_15_minutes() -> None:
    agent, _, now, logs = make_agent([SendResult("retry", 500)] * 3)
    agent.tick()
    now[0] += BUFFER_MAX_AGE_S + 1
    agent.tick()
    assert len(agent.queue) == 1  # eskisi tashlandi, yangisi qoldi
    assert any("tashlandi" in line for line in logs)


def test_facts_are_sent_only_in_first_batch() -> None:
    agent, _, _, _ = make_agent([SendResult("retry", 500)])
    agent.tick()
    agent.tick()
    first, second = agent.queue
    assert first.facts and not second.facts


def test_run_stops_after_count() -> None:
    agent, sender, _, _ = make_agent([])
    sleeps: list[float] = []
    run(agent, interval=15, count=3, sleep=sleeps.append)
    assert len(sender.sent) == 3 and len(sleeps) == 2


# ---------- enroll ----------
def test_enroll_returns_permanent_token(stub: tuple[type[_Stub], str]) -> None:
    handler, url = stub
    handler.queued = [
        (200, {}, b'{"host_id": "h-1", "agent_token": "agt_x", "interval_seconds": 15}')
    ]
    result = enroll(url, "enr_one", {"hostname": "vm1", "os": "Linux"})
    assert (result.host_id, result.agent_token, result.interval_seconds) == ("h-1", "agt_x", 15)
    assert handler.received[0]["enroll_token"] == "enr_one"
    assert handler.received[0]["hostname"] == "vm1"
    assert "Authorization" not in handler.headers_seen[0]


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "invalid_enroll_token"), (409, "host_already_enrolled"), (410, "enroll_token_expired")],
)
def test_enroll_errors_carry_core_code(
    stub: tuple[type[_Stub], str], status: int, code: str
) -> None:
    handler, url = stub
    handler.queued = [(status, {}, json.dumps({"code": code, "message": "x"}).encode())]
    with pytest.raises(EnrollError) as info:
        enroll(url, "enr_bad", {})
    assert (info.value.code, info.value.status) == (code, status)


def test_enroll_network_and_malformed_response() -> None:
    with pytest.raises(EnrollError, match="ulanib bo'lmadi"):
        enroll("http://127.0.0.1:9", "enr", {}, timeout=1.0)


def test_enroll_rejects_malformed_success(stub: tuple[type[_Stub], str]) -> None:
    handler, url = stub
    handler.queued = [(200, {}, b'{"host_id": "h-1"}')]
    with pytest.raises(EnrollError, match="javob noto'g'ri"):
        enroll(url, "enr", {})


def _args(**kw: str) -> argparse.Namespace:
    base = {"url": "http://x", "token": "", "token_file": "", "enroll_token": ""}
    return argparse.Namespace(**{**base, **kw})


def test_resolve_token_prefers_explicit_then_file(tmp_path: Path) -> None:
    assert resolve_token(_args(token="agt_a")) == "agt_a"
    saved = tmp_path / "token"
    saved.write_text("agt_saved\n", encoding="utf-8")
    assert resolve_token(_args(token_file=str(saved), enroll_token="enr_unused")) == "agt_saved"
    assert resolve_token(_args()) is None


def test_resolve_token_enrolls_once_and_persists_with_0600(
    stub: tuple[type[_Stub], str], tmp_path: Path
) -> None:
    handler, url = stub
    handler.queued = [
        (200, {}, b'{"host_id": "h-1", "agent_token": "agt_new", "interval_seconds": 15}')
    ]
    path = tmp_path / "token"
    args = _args(url=url, token_file=str(path), enroll_token="enr_one")
    assert resolve_token(args) == "agt_new"
    assert path.read_text(encoding="utf-8").strip() == "agt_new"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    assert resolve_token(args) == "agt_new"  # ikkinchi marta enroll qilinmaydi
    assert len(handler.received) == 1
