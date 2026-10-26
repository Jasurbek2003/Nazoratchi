"""appctl `state.json` / `_run.json` sinovlari (E-01, TZ 10.3.1–10.3.3).

Haqiqiy `appctl` soxta `docker`, `rsync` va `date` (hafta kuni) bilan ishga tushiriladi: serverga,
Docker'ga va tarmoqqa tegmaydi. Asl skript (`appctl.orig`) bilan solishtirish R-109 uchun:
yangi kod zaxirani buzmasligi shart.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent.parent
NEW = HERE / "appctl"
ORIG = HERE / "appctl.orig"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash kerak")

DOCKER_STUB = """#!/usr/bin/env bash
case "$*" in
  *pg_dump*)
    case "${FAKE_PG:-ok}" in
      ok)    head -c 6000 /dev/urandom | base64; exit 0 ;;
      small) echo tiny; exit 0 ;;
      fail)  echo "pg_dump: error: connection to server failed" >&2; exit 1 ;;
      weird) printf 'pg_dump: "quoted" back\\\\slash\\ttab\\nikkinchi qator Ўзбек password=hunter2 Authorization: Bearer agt_secret123\\n' >&2; exit 1 ;;
      long)  printf 'x%.0s' $(seq 1 600) >&2; exit 1 ;;
      hang)  sleep 30; exit 0 ;;
    esac ;;
  *) exit 0 ;;
esac
"""
RSYNC_STUB = """#!/usr/bin/env bash
echo "$*" > "${STUB_DIR}/rsync.args"
if [ "${FAKE_RSYNC:-ok}" = ok ]; then
  echo "Number of files: 12"; echo "Total bytes sent: 51,237,892"; exit 0
fi
echo "ssh: connect to host 203.0.113.5 port 22: Connection refused"; exit 255
"""
DATE_STUB = """#!/usr/bin/env bash
if [ "$*" = "+%u" ] && [ -n "${FAKE_DOW:-}" ]; then echo "$FAKE_DOW"; else exec "$REAL_DATE" "$@"; fi
"""


def posix(path: Path) -> str:
    """tar `C:/...` dagi ikki nuqtani masofaviy host deb o'qiydi (Windows/MSYS); `/c/...` ko'rinishi kerak."""
    text = path.as_posix()
    if os.name == "nt" and len(text) > 1 and text[1] == ":":
        return f"/{text[0].lower()}{text[2:]}"
    return text


@dataclass
class Ctx:
    base: Path
    stubs: Path

    @property
    def backups(self) -> Path:
        return self.base / "backups"

    def appctl(self, project: str, **variables: str) -> None:
        lines = [f'{k}="{v}"' for k, v in variables.items()]
        (self.base / "projects" / project / ".appctl").write_text("\n".join(lines) + "\n")

    def run(self, script: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        assert BASH is not None
        full = {
            **os.environ,
            "APPCTL_BASE": posix(self.base),
            "STUB_DIR": posix(self.stubs),
            "REAL_DATE": shutil.which("date") or "/usr/bin/date",
            "PATH": f"{self.stubs}{os.pathsep}{os.environ['PATH']}",
            **env,
        }
        return subprocess.run(
            [BASH, script.as_posix(), *args], env=full, capture_output=True, text=True, timeout=60
        )

    def state(self, project: str) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.backups / project / "state.json").read_text())
        return data

    def run_json(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.backups / "_run.json").read_text())
        return data


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("docker", DOCKER_STUB), ("rsync", RSYNC_STUB), ("date", DATE_STUB)):
        path = stubs / name
        path.write_text(body, newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    base = tmp_path / "opt"
    for project in ("Alpha", "Static"):
        directory = base / "projects" / project
        directory.mkdir(parents=True)
        (directory / "docker-compose.yml").write_text("services: {}\n")
    context = Ctx(base, stubs)
    context.appctl("Alpha", DB_SERVICE="db", DB_USER="u", DB_NAME="n")
    return context


# ---------------------------------------------------------------- muvaffaqiyatli zaxira
def test_state_json_after_successful_backup(ctx: Ctx) -> None:
    result = ctx.run(NEW, "backup", "Alpha")
    assert result.returncode == 0, result.stderr
    state = ctx.state("Alpha")
    assert state["schema"] == 1 and state["project"] == "Alpha" and state["status"] == "ok"
    assert state["host"] and state["duration_s"] >= 0
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", state["started_at"])
    assert state["started_at"] <= state["finished_at"]
    daily = state["daily"]
    assert daily["status"] == "ok" and daily["error"] is None
    assert re.fullmatch(r"Alpha-\d{8}-\d{6}\.sql\.gz", daily["file"])
    real = ctx.backups / "Alpha" / "daily" / daily["file"]
    assert daily["size_bytes"] == real.stat().st_size > 1024
    assert state["weekly_files"] is None
    leftovers = [p for p in ctx.backups.rglob("*") if p.name.endswith(".tmp")]
    assert leftovers == []


def test_project_without_db_reports_null_daily(ctx: Ctx) -> None:
    assert ctx.run(NEW, "backup", "Static").returncode == 0
    state = ctx.state("Static")
    assert state["status"] == "ok" and state["daily"] is None and state["weekly_files"] is None


def test_single_project_backup_does_not_write_run_json(ctx: Ctx) -> None:
    ctx.run(NEW, "backup", "Alpha")
    assert not (ctx.backups / "_run.json").exists()


# ---------------------------------------------------------------- xatolar
@pytest.mark.parametrize(
    ("mode", "needle"),
    [("fail", "connection to server failed"), ("small", "1024")],
)
def test_failed_dump_is_reported(ctx: Ctx, mode: str, needle: str) -> None:
    result = ctx.run(NEW, "backup", "Alpha", FAKE_PG=mode)
    assert result.returncode == 1
    state = ctx.state("Alpha")
    assert state["status"] == "fail" and state["daily"]["status"] == "fail"
    assert state["daily"]["file"] is None and state["daily"]["size_bytes"] == 0
    assert needle in state["daily"]["error"]
    assert list((ctx.backups / "Alpha" / "daily").iterdir()) == []  # qoldiq fayl yo'q


def test_error_text_is_json_safe_masked_and_truncated(ctx: Ctx) -> None:
    ctx.run(NEW, "backup", "Alpha", FAKE_PG="weird")
    raw = (ctx.backups / "Alpha" / "state.json").read_text()
    error = json.loads(raw)["daily"]["error"]  # JSON yaroqli
    assert "hunter2" not in raw and "agt_secret123" not in raw
    assert "password=***" in error and "Authorization: Bearer ***" in error
    assert "\n" not in error and '"quoted"' in error and "back\\slash" in error
    ctx.run(NEW, "backup", "Alpha", FAKE_PG="long")
    assert len(ctx.state("Alpha")["daily"]["error"]) <= 300


def test_retention_runs_after_success_but_not_after_failed_dump(ctx: Ctx) -> None:
    daily = ctx.backups / "Alpha" / "daily"
    daily.mkdir(parents=True)
    old = daily / "Alpha-old.sql.gz"
    old.write_bytes(b"x")
    ten_days_ago = time.time() - 10 * 86400
    os.utime(old, (ten_days_ago, ten_days_ago))
    ctx.run(NEW, "backup", "Alpha", FAKE_PG="fail")
    assert old.exists()  # asl xatti-harakat: xato bo'lsa tozalash o'tkazib yuboriladi
    ctx.run(NEW, "backup", "Alpha")
    assert not old.exists()


# ---------------------------------------------------------------- haftalik fayllar
def test_weekly_files_on_sunday(ctx: Ctx, tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_text("salom")
    ctx.appctl("Alpha", DB_SERVICE="db", DB_USER="u", DB_NAME="n", BACKUP_PATHS=posix(data))
    assert ctx.run(NEW, "backup", "Alpha", FAKE_DOW="7").returncode == 0
    weekly = ctx.state("Alpha")["weekly_files"]
    assert weekly["status"] == "ok" and re.fullmatch(r"Alpha-files-\d{8}-\d{6}\.tar\.gz", weekly["file"])
    assert weekly["size_bytes"] == (ctx.backups / "Alpha" / "weekly" / weekly["file"]).stat().st_size


def test_no_weekly_files_on_other_days(ctx: Ctx, tmp_path: Path) -> None:
    ctx.appctl("Alpha", DB_SERVICE="db", DB_USER="u", DB_NAME="n", BACKUP_PATHS=posix(tmp_path))
    ctx.run(NEW, "backup", "Alpha", FAKE_DOW="3")
    assert ctx.state("Alpha")["weekly_files"] is None


def test_failed_tar_is_reported_and_fails_the_run(ctx: Ctx, tmp_path: Path) -> None:
    missing = posix(tmp_path / "yoq-papka")
    ctx.appctl("Alpha", DB_SERVICE="db", DB_USER="u", DB_NAME="n", BACKUP_PATHS=missing)
    result = ctx.run(NEW, "backup", "Alpha", FAKE_DOW="7")
    state = ctx.state("Alpha")
    assert result.returncode == 1  # ASL skript bu holda 0 qaytarardi (jim nosozlik)
    assert state["status"] == "fail" and state["daily"]["status"] == "ok"
    assert state["weekly_files"]["status"] == "fail" and state["weekly_files"]["error"]
    assert list((ctx.backups / "Alpha" / "weekly").glob("*files*")) == []
    assert ctx.run(ORIG, "backup", "Alpha", FAKE_DOW="7").returncode == 0  # farqni qayd etadi


# ---------------------------------------------------------------- _run.json va offsite
def test_run_json_without_offsite(ctx: Ctx) -> None:
    assert ctx.run(NEW, "backup", "all").returncode == 0
    run = ctx.run_json()
    assert run["schema"] == 1 and re.fullmatch(r"\d{8}-\d{6}", run["run_id"])
    assert run["projects"] == [
        {"name": "Alpha", "status": "ok"},
        {"name": "Static", "status": "ok"},
    ]
    assert run["offsite"] == {
        "configured": False,
        "status": None,
        "target_host": None,
        "exit_code": None,
        "finished_at": None,
        "bytes_sent": None,
    }


def test_run_json_records_failed_project(ctx: Ctx) -> None:
    assert ctx.run(NEW, "backup", "all", FAKE_PG="fail").returncode == 1
    statuses = {p["name"]: p["status"] for p in ctx.run_json()["projects"]}
    assert statuses == {"Alpha": "fail", "Static": "ok"}


def test_offsite_success(ctx: Ctx) -> None:
    (ctx.base / "appctl.conf").write_text('OFFSITE="backup@203.0.113.5:/srv/backups/main-server"\n')
    assert ctx.run(NEW, "backup", "all").returncode == 0
    offsite = ctx.run_json()["offsite"]
    assert offsite["configured"] is True and offsite["status"] == "ok" and offsite["exit_code"] == 0
    assert offsite["target_host"] == "203.0.113.5" and offsite["bytes_sent"] == 51237892
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", offsite["finished_at"])
    assert "--stats" in (ctx.stubs / "rsync.args").read_text()


def test_offsite_failure(ctx: Ctx) -> None:
    (ctx.base / "appctl.conf").write_text('OFFSITE="backup@203.0.113.5:/srv/backups/main-server"\n')
    result = ctx.run(NEW, "backup", "all", FAKE_RSYNC="fail")
    assert result.returncode == 1
    offsite = ctx.run_json()["offsite"]
    assert offsite["status"] == "fail" and offsite["exit_code"] == 255 and offsite["bytes_sent"] is None
    assert "Connection refused" in result.stdout  # rsync chiqishi logda ko'rinadi


def test_offsite_host_without_user(ctx: Ctx) -> None:
    (ctx.base / "appctl.conf").write_text('OFFSITE="203.0.113.5:/srv/b"\n')
    ctx.run(NEW, "backup", "all")
    assert ctx.run_json()["offsite"]["target_host"] == "203.0.113.5"


# ---------------------------------------------------------------- R-109: zaxirani buzmaslik
def test_state_write_failure_never_breaks_the_backup(ctx: Ctx) -> None:
    (ctx.backups / "Alpha" / "state.json.tmp").mkdir(parents=True)  # yozishga to'sqinlik
    result = ctx.run(NEW, "backup", "Alpha")
    assert result.returncode == 0
    assert "state.json yozilmadi" in result.stderr
    assert len(list((ctx.backups / "Alpha" / "daily").glob("*.sql.gz"))) == 1


def test_run_write_failure_never_breaks_the_backup(ctx: Ctx) -> None:
    (ctx.backups).mkdir(parents=True)
    (ctx.backups / "_run.json.tmp").mkdir()
    result = ctx.run(NEW, "backup", "all")
    assert result.returncode == 0 and "_run.json yozilmadi" in result.stderr


@pytest.mark.parametrize("fake_pg", ["ok", "fail", "small"])
def test_exit_code_and_dump_match_original_script(ctx: Ctx, fake_pg: str) -> None:
    """Yangi skript asl skript bilan bir xil natija beradi (faqat tar xatosi bundan mustasno)."""
    results = {}
    for name, script in (("orig", ORIG), ("new", NEW)):
        shutil.rmtree(ctx.backups, ignore_errors=True)
        proc = ctx.run(script, "backup", "Alpha", FAKE_PG=fake_pg)
        dumps = list((ctx.backups / "Alpha" / "daily").glob("*.sql.gz"))
        results[name] = (proc.returncode, len(dumps))
    assert results["orig"] == results["new"]


def test_broken_appctl_file_fails_the_project_not_the_run(ctx: Ctx) -> None:
    """Asl skript: buzuq .appctl xabar chiqarib, loyihani `ok` (dump o'tkazib yuborilgan) qoldirardi."""
    (ctx.base / "projects" / "Alpha" / ".appctl").write_text("DB_SERVICE=(\n")
    new = ctx.run(NEW, "backup", "all")
    assert new.returncode == 1
    assert ctx.state("Alpha")["status"] == "fail" and ctx.state("Static")["status"] == "ok"
    old = ctx.run(ORIG, "backup", "all")
    assert old.returncode == 0  # jim nosozlik: asl skript buni xato deb hisoblamaydi
