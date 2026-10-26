"""appctl heartbeat sinovlari (E-03, TZ 9.14, 10.3.5).

Haqiqiy `curl` va haqiqiy mahalliy HTTP server bilan; `docker`/`rsync` soxta (test_state.py dagi stublar).
Asosiy talab (R-109): heartbeat zaxira natijasini, fayllarni va chiqish kodini HECH QACHON o'zgartirmaydi.
"""

import json
import os
import shutil
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from test_state import BASH, NEW, Ctx, ctx  # noqa: F401  (ctx — fixture)

pytestmark = pytest.mark.skipif(BASH is None or shutil.which("curl") is None, reason="bash va curl kerak")

TOKEN = "SIRTOKEN123"


class Hub(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests: list[str] = []
        self.status = 200
        self.delay = 0.0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/hb/{TOKEN}"

    def queries(self) -> list[dict[str, list[str]]]:
        return [parse_qs(urlsplit(p).query, keep_blank_values=True) for p in self.requests]


class _Handler(BaseHTTPRequestHandler):
    server: Hub

    def do_GET(self) -> None:  # noqa: N802
        self.server.requests.append(self.path)
        if self.server.delay:
            time.sleep(self.server.delay)
        self.send_response(self.server.status)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def hub() -> Iterator[Hub]:
    server = Hub()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def configure(ctx: Ctx, url: str, **extra: str) -> None:
    lines = [f"HEARTBEAT_URL='{url}'"] + [f"{k}={v}" for k, v in extra.items()]
    (ctx.base / "appctl.secret").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- backup all -> heartbeat
def test_no_heartbeat_when_not_configured(ctx: Ctx, hub: Hub) -> None:
    assert ctx.run(NEW, "backup", "all").returncode == 0
    assert hub.requests == []


def test_ok_heartbeat_after_successful_backup_all(ctx: Ctx, hub: Hub) -> None:
    configure(ctx, hub.url)
    assert ctx.run(NEW, "backup", "all").returncode == 0
    assert len(hub.requests) == 1 and hub.requests[0].startswith(f"/hb/{TOKEN}?")
    query = hub.queries()[0]
    assert query["status"] == ["ok"] and int(query["duration"][0]) >= 0 and "msg" not in query


def test_fail_heartbeat_names_failed_projects(ctx: Ctx, hub: Hub) -> None:
    configure(ctx, hub.url)
    proc = ctx.run(NEW, "backup", "all", FAKE_PG="fail")
    assert proc.returncode == 1  # asl xatti-harakat saqlanadi
    assert len(hub.requests) == 1
    query = hub.queries()[0]
    assert query["status"] == ["fail"] and query["msg"] == ["fail: Alpha"]


def test_offsite_failure_is_named_in_message(ctx: Ctx, hub: Hub) -> None:
    (ctx.base / "appctl.conf").write_text('OFFSITE="backup@203.0.113.5:/srv/b"\n')
    configure(ctx, hub.url)
    ctx.run(NEW, "backup", "all", FAKE_RSYNC="fail")
    assert hub.queries()[0]["msg"] == ["fail: offsite"]
    hub.requests.clear()
    ctx.run(NEW, "backup", "all", FAKE_RSYNC="fail", FAKE_PG="fail")
    assert hub.queries()[0]["msg"] == ["fail: Alpha,offsite"]


def test_single_project_backup_sends_no_heartbeat(ctx: Ctx, hub: Hub) -> None:
    configure(ctx, hub.url)
    ctx.run(NEW, "backup", "Alpha")
    assert hub.requests == []


def test_heartbeat_can_live_in_appctl_conf_too(ctx: Ctx, hub: Hub) -> None:
    (ctx.base / "appctl.conf").write_text(f"HEARTBEAT_URL='{hub.url}'\n")
    ctx.run(NEW, "backup", "all")
    assert len(hub.requests) == 1


# ---------------------------------------------------------------- R-109: zaxirani buzmaslik
def test_unreachable_core_never_affects_backup(ctx: Ctx) -> None:
    configure(ctx, f"http://127.0.0.1:9/hb/{TOKEN}")  # port yopiq
    proc = ctx.run(NEW, "backup", "all")
    assert proc.returncode == 0
    assert "heartbeat yuborilmadi" in proc.stderr
    assert TOKEN not in proc.stdout + proc.stderr  # token hech qachon chop etilmaydi
    assert ctx.state("Alpha")["status"] == "ok" and ctx.run_json()["projects"]
    assert len(list((ctx.backups / "Alpha" / "daily").glob("*.sql.gz"))) == 1


def test_http_error_is_reported_without_token_and_exit_code_unchanged(ctx: Ctx, hub: Hub) -> None:
    hub.status = 500
    configure(ctx, hub.url)
    proc = ctx.run(NEW, "backup", "all")
    assert proc.returncode == 0 and "heartbeat yuborilmadi" in proc.stderr
    assert TOKEN not in proc.stdout + proc.stderr


def test_slow_core_is_bounded_by_timeout(ctx: Ctx, hub: Hub) -> None:
    t0 = time.monotonic()
    ctx.run(NEW, "backup", "all")
    baseline = time.monotonic() - t0
    hub.delay = 8.0
    configure(ctx, hub.url, HEARTBEAT_TIMEOUT="1")
    t0 = time.monotonic()
    proc = ctx.run(NEW, "backup", "all")
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0 and "heartbeat yuborilmadi" in proc.stderr
    assert elapsed < baseline + 4.0, (elapsed, baseline)  # 8 s kutilmadi


def test_broken_project_config_fails_only_that_project(ctx: Ctx, hub: Hub) -> None:
    """Buzuq `.appctl`: asl skript loyihani jimgina "ok" qoldirardi. Endi fail, qolganlari zaxiralanadi."""
    broken = ctx.base / "projects" / "Broken"
    broken.mkdir()
    (broken / "docker-compose.yml").write_text("services: {}\n")
    (broken / ".appctl").write_text("DB_SERVICE=(\n")  # sintaksis xatosi
    configure(ctx, hub.url)
    proc = ctx.run(NEW, "backup", "all")
    assert proc.returncode == 1
    assert ctx.state("Broken")["status"] == "fail" and ".appctl" in ctx.state("Broken")["daily"]["error"]
    assert ctx.state("Alpha")["status"] == "ok"  # boshqa loyiha zaxirasi to'xtamadi
    statuses = {p["name"]: p["status"] for p in ctx.run_json()["projects"]}
    assert statuses["Broken"] == "fail" and statuses["Alpha"] == "ok"
    assert len(hub.requests) == 1 and hub.queries()[0]["msg"] == ["fail: Broken"]


@pytest.mark.skipif(os.name == "nt", reason="Windows'da TerminateProcess EXIT tuzog'ini ishga tushirmaydi")
def test_killed_run_sends_exactly_one_fail_heartbeat(ctx: Ctx, hub: Hub) -> None:
    """cron/reboot SIGTERM yuborsa, jimlik o'rniga "fail" ketadi (AL-048 vs AL-047)."""
    import signal
    import subprocess

    configure(ctx, hub.url)
    assert BASH is not None
    env = {
        **os.environ,
        "APPCTL_BASE": ctx.base.as_posix(),
        "STUB_DIR": ctx.stubs.as_posix(),
        "REAL_DATE": shutil.which("date") or "/usr/bin/date",
        "PATH": f"{ctx.stubs}{os.pathsep}{os.environ['PATH']}",
        "FAKE_PG": "hang",
    }
    proc = subprocess.Popen(
        [BASH, NEW.as_posix(), "backup", "all"],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    time.sleep(1.5)  # soxta pg_dump "osilib" turibdi
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)  # cron/systemd butun guruhni to'xtatadi
    proc.wait(timeout=20)
    deadline = time.monotonic() + 10
    while not hub.requests and time.monotonic() < deadline:
        time.sleep(0.1)
    stderr = proc.stderr.read() if proc.stderr else ""
    assert len(hub.requests) == 1, (proc.returncode, stderr)
    query = hub.queries()[0]
    assert query["status"] == ["fail"] and "to'xtatildi" in query["msg"][0] and "143" in query["msg"][0]


def test_successful_run_does_not_send_twice(ctx: Ctx, hub: Hub) -> None:
    configure(ctx, hub.url)
    ctx.run(NEW, "backup", "all")
    assert len(hub.requests) == 1  # EXIT tuzog'i qo'shimcha "fail" yubormaydi


# ---------------------------------------------------------------- appctl heartbeat (qo'lda)
def test_manual_heartbeat_command(ctx: Ctx, hub: Hub) -> None:
    configure(ctx, hub.url)
    proc = ctx.run(NEW, "heartbeat")
    assert proc.returncode == 0 and "yuborildi" in proc.stdout
    assert hub.queries()[0] == {"status": ["ok"]}


def test_manual_heartbeat_requires_configuration_and_valid_status(ctx: Ctx) -> None:
    proc = ctx.run(NEW, "heartbeat")
    assert proc.returncode == 1 and "sozlanmagan" in proc.stderr
    configure(ctx, "http://127.0.0.1:9/hb/x")
    assert ctx.run(NEW, "heartbeat", "xato").returncode == 1


def test_manual_heartbeat_reports_failure_with_exit_code(ctx: Ctx) -> None:
    configure(ctx, f"http://127.0.0.1:9/hb/{TOKEN}")
    proc = ctx.run(NEW, "heartbeat", "ok")
    assert proc.returncode == 1 and TOKEN not in proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "message",
    ["oddiy", "a b&c=d/e", "50% + #hash ?x=1", "O'zbek Ўзбек ñ", "x" * 250],
)
def test_message_is_url_encoded_and_truncated(ctx: Ctx, hub: Hub, message: str) -> None:
    configure(ctx, hub.url)
    ctx.run(NEW, "heartbeat", "fail", message)
    got = hub.queries()[0]["msg"][0]
    assert got == message[:200]
    assert hub.queries()[0]["status"] == ["fail"]


# ---------------------------------------------------------------- heartbeat-set
def test_heartbeat_set_writes_secret_file_idempotently(ctx: Ctx) -> None:
    secret = ctx.base / "appctl.secret"
    secret.write_text("HEARTBEAT_TIMEOUT=7\nHEARTBEAT_URL='https://eski.example.uz/hb/OLD'\n")
    proc = ctx.run(NEW, "heartbeat-set", "https://core.example.uz/hb/NEW123?x=1&y=2")
    assert proc.returncode == 0 and "NEW123" not in proc.stdout + proc.stderr
    lines = secret.read_text().splitlines()
    assert lines.count("HEARTBEAT_TIMEOUT=7") == 1  # boshqa qatorlar saqlanadi
    assert [line for line in lines if line.startswith("HEARTBEAT_URL=")] == [
        "HEARTBEAT_URL='https://core.example.uz/hb/NEW123?x=1&y=2'"
    ]
    assert ctx.run(NEW, "heartbeat-set", "https://core.example.uz/hb/NEW123?x=1&y=2").returncode == 0
    assert len([ln for ln in secret.read_text().splitlines() if ln.startswith("HEARTBEAT_URL=")]) == 1


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://core.example.uz/hb/T",  # https shart
        "https://x/hb/t'; touch /tmp/pwned; '",
        "https://x/$(id)",
        "https://x/`id`",
        "https://x/a b",
        'https://x/a"b',
        "https://x/a\\b",
        "ftp://x/hb/t",
    ],
)
def test_heartbeat_set_rejects_unsafe_urls(ctx: Ctx, url: str) -> None:
    proc = ctx.run(NEW, "heartbeat-set", url)
    assert proc.returncode == 1
    assert not (ctx.base / "appctl.secret").exists()


def test_secret_url_is_picked_up_by_backup(ctx: Ctx, hub: Hub) -> None:
    """heartbeat-set yozgan fayl appctl tomonidan o'qiladi (https bo'lgani uchun faqat o'qilishi tekshiriladi)."""
    ctx.run(NEW, "heartbeat-set", "https://core.example.uz/hb/ABC")
    text = (ctx.base / "appctl.secret").read_text()
    assert text == "HEARTBEAT_URL='https://core.example.uz/hb/ABC'\n"
    assert json.dumps(text)  # fayl yaroqli matn
    assert os.path.exists(ctx.base / "appctl.secret")
    _ = Any
