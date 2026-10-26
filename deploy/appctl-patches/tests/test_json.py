"""appctl `list --json` va `status --json` sinovlari (E-02, TZ 18.1).

Soxta `docker`, `df`, `free`, `openssl` bilan deterministik. Inson o'qiydigan `list`/`status` chiqishi
asl skript bilan solishtiriladi: yangi kod uni o'zgartirmasligi kerak (R-109).
"""

import json
import os
import re
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_state import BASH, NEW, ORIG, Ctx, posix  # noqa: F401  (pytest tests/ ni sys.path ga qo'shadi)

pytestmark = pytest.mark.skipif(BASH is None, reason="bash kerak")

DOCKER = """#!/usr/bin/env bash
if [ -n "${FAKE_DOCKER_DOWN:-}" ]; then echo "Cannot connect to the Docker daemon" >&2; exit 1; fi
proj="$(basename "$PWD")"
case "$*" in
  *"ps -a --format"*) printf '%b' "${FAKE_CONTAINERS:-}" ;;
  *"ps --status running -q"*) v="FAKE_RUN_$proj"; printf '%b' "${!v:-}" ;;
  *"ps -a -q"*) v="FAKE_ALL_$proj"; printf '%b' "${!v:-}" ;;
  *) exit 0 ;;
esac
"""
DF = """#!/usr/bin/env bash
if [ -n "${FAKE_NO_DF:-}" ]; then exit 1; fi
case "$*" in
  *-B1*) echo "Filesystem     1-blocks        Used   Available Capacity Mounted on"
         echo "${FAKE_DF_NAME:-/dev/sda1}   85899345920 66993537024 18905808896      78% /" ;;
  *) echo "Filesystem Size Used Avail Use% Mounted on"; echo "/dev/sda1 80G 62G 18G 78% /" ;;
esac
"""
FREE = """#!/usr/bin/env bash
echo "               total        used        free      shared  buff/cache   available"
echo "Mem:      8321499136  3000000000  1000000000      100000  4000000000  4842575872"
echo "Swap:              0           0           0"
"""
# `openssl x509 -enddate`: cert.pem fayl nomidagi kun sonini o'qiydi (cert-41 -> 41 kun + 1 soat)
OPENSSL = """#!/usr/bin/env bash
file="${@: -1}"
case "$file" in
  *broken*) exit 1 ;;
  *) d="$(basename "$(dirname "$file")")"; d="${d#cert-}"
     echo "notAfter=$(date -u -d "+${d} days 1 hour" '+%b %e %H:%M:%S %Y GMT')" ;;
esac
"""

CONTAINERS = (
    "nazar-web-1\\tUp 2 days (healthy)\\n"
    "nazar-db-1\\tUp 4 days\\n"
    "old-job\\tExited (1) 3 hours ago\\n"
    "worker\\tUp 5 minutes (health: starting)\\n"
    "api\\tUp 1 hour (unhealthy)\\n"
)


@pytest.fixture
def jctx(tmp_path: Path) -> Ctx:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("docker", DOCKER), ("df", DF), ("free", FREE), ("openssl", OPENSSL)):
        path = stubs / name
        path.write_text(body, newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    base = tmp_path / "opt"
    for project in ("Alpha", "Static", "Down"):
        directory = base / "projects" / project
        directory.mkdir(parents=True)
        (directory / "docker-compose.yml").write_text("services: {}\n")
    context = Ctx(base, stubs)
    context.appctl("Alpha", DB_SERVICE="db", DB_USER="u", DB_NAME="n")
    return context


LIST_ENV = {
    "FAKE_ALL_Alpha": "a1\\na2\\na3\\n",
    "FAKE_RUN_Alpha": "a1\\na2\\na3\\n",
    "FAKE_ALL_Static": "s1\\ns2\\n",
    "FAKE_RUN_Static": "s1\\n",
    "FAKE_ALL_Down": "d1\\nd2\\n",  # konteynerlar bor, hech biri ishlamayapti
    "FAKE_RUN_Down": "",
}


def as_json(proc: Any) -> dict[str, Any]:
    assert proc.returncode == 0, proc.stderr
    data: dict[str, Any] = json.loads(proc.stdout)  # stdout FAQAT JSON bo'lishi kerak
    return data


def by_name(items: list[dict[str, Any]], key: str = "name") -> dict[str, dict[str, Any]]:
    return {i[key]: i for i in items}


# ---------------------------------------------------------------- list --json
def test_list_json_schema_and_states(jctx: Ctx) -> None:
    proc = jctx.run(NEW, "list", "--json", **LIST_ENV)
    assert proc.returncode == 0, proc.stderr
    data = as_json(proc)
    assert data["schema"] == 1 and data["host"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["generated_at"])
    projects = by_name(data["projects"])
    assert set(projects) == {"Alpha", "Static", "Down"}
    alpha = projects["Alpha"]
    assert alpha == {
        "name": "Alpha",
        "compose_file": "docker-compose.yml",
        "compose_extra": None,
        "state": "running",
        "running": 3,
        "total": 3,
        "health_url": None,
        "db": {"service": "db", "user": "u", "name": "n"},
        "backup_paths": [],
    }
    assert (projects["Static"]["state"], projects["Static"]["running"], projects["Static"]["total"]) == (
        "partial",
        1,
        2,
    )
    assert projects["Static"]["db"] is None
    assert (projects["Down"]["state"], projects["Down"]["running"], projects["Down"]["total"]) == (
        "stopped",
        0,
        2,
    )


def test_list_json_project_options(jctx: Ctx) -> None:
    jctx.appctl(
        "Alpha",
        DB_SERVICE="db",
        DB_USER="u",
        DB_NAME="n",
        COMPOSE_EXTRA="docker-compose.server.yml",
        HEALTH_URL="http://127.0.0.1:8020/healthz/?token=abc123",
        HEALTH_CURL_OPTS="-H Authorization:Bearer-sir",
        BACKUP_PATHS="/var/media /var/minio",
    )
    proc = jctx.run(NEW, "list", "--json", **LIST_ENV)
    alpha = by_name(as_json(proc)["projects"])["Alpha"]
    assert alpha["compose_extra"] == "docker-compose.server.yml"
    assert alpha["backup_paths"] == ["/var/media", "/var/minio"]
    assert alpha["health_url"] == "http://127.0.0.1:8020/healthz/?token=***"  # maxfiy yopildi
    assert "Bearer-sir" not in proc.stdout and "abc123" not in proc.stdout  # HEALTH_CURL_OPTS chiqmaydi


def test_list_json_state_is_unknown_when_docker_is_down(jctx: Ctx) -> None:
    proc = jctx.run(NEW, "list", "--json", FAKE_DOCKER_DOWN="1")
    assert proc.returncode == 0
    assert {p["state"] for p in as_json(proc)["projects"]} == {"unknown"}


def test_list_json_without_projects(jctx: Ctx) -> None:
    for p in (jctx.base / "projects").iterdir():
        (p / "docker-compose.yml").unlink()
    assert as_json(jctx.run(NEW, "list", "--json"))["projects"] == []


def test_list_json_nothing_but_json_on_stdout(jctx: Ctx) -> None:
    proc = jctx.run(NEW, "list", "--json", **LIST_ENV)
    assert proc.stdout.startswith("{") and proc.stdout.endswith("}\n") and proc.stdout.count("\n") == 1


def test_unknown_flag_fails(jctx: Ctx) -> None:
    for cmd in ("list", "status"):
        proc = jctx.run(NEW, cmd, "--bogus")
        assert proc.returncode == 1 and "noma'lum bayroq" in proc.stderr


def test_human_list_and_status_output_unchanged(jctx: Ctx) -> None:
    (jctx.base / "backups" / "Alpha" / "daily").mkdir(parents=True)
    (jctx.base / "backups" / "Alpha" / "daily" / "Alpha-1.sql.gz").write_bytes(b"x")
    for cmd in ("list", "status"):
        old = jctx.run(ORIG, cmd, **LIST_ENV, APPCTL_LETSENCRYPT=posix(jctx.base / "yoq"))
        new = jctx.run(NEW, cmd, **LIST_ENV, APPCTL_LETSENCRYPT=posix(jctx.base / "yoq"))
        assert (old.returncode, old.stdout) == (new.returncode, new.stdout), cmd


# ---------------------------------------------------------------- status --json
def make_certs(jctx: Ctx, *names: str) -> Path:
    live = jctx.base / "le"
    for name in names:
        (live / name).mkdir(parents=True)
        (live / name / "cert.pem").write_text("fake")
    return live


def test_status_json_disk_memory_containers(jctx: Ctx) -> None:
    proc = jctx.run(NEW, "status", "--json", FAKE_CONTAINERS=CONTAINERS)
    assert proc.returncode == 0, proc.stderr
    data = as_json(proc)
    assert data["schema"] == 1 and data["host"]
    assert data["disk"] == {
        "mount": "/",
        "total_bytes": 85899345920,
        "used_bytes": 66993537024,
        "used_percent": 78,
    }
    # used = total - available (TZ 18.1.2 namunasi bilan bir xil formula)
    assert data["memory"] == {
        "total_bytes": 8321499136,
        "used_bytes": 8321499136 - 4842575872,
        "available_bytes": 4842575872,
    }
    containers = by_name(data["containers"])
    assert containers["nazar-web-1"] == {
        "name": "nazar-web-1",
        "status": "Up 2 days (healthy)",
        "running": True,
        "health": "healthy",
    }
    assert containers["nazar-db-1"]["health"] is None and containers["nazar-db-1"]["running"] is True
    assert containers["old-job"]["running"] is False
    assert containers["worker"]["health"] == "starting"
    assert containers["api"]["health"] == "unhealthy"


def test_status_json_disk_parses_filesystem_names_with_spaces(jctx: Ctx) -> None:
    proc = jctx.run(NEW, "status", "--json", FAKE_DF_NAME="C:/Program Files/Git")
    assert as_json(proc)["disk"]["total_bytes"] == 85899345920


def test_status_json_certificates(jctx: Ctx) -> None:
    live = make_certs(jctx, "cert-41", "cert-3", "broken")
    proc = jctx.run(NEW, "status", "--json", APPCTL_LETSENCRYPT=posix(live))
    certs = by_name(as_json(proc)["certificates"])
    assert set(certs) == {"cert-41", "cert-3"}  # o'qilmaydigani tushib qoladi
    assert certs["cert-41"]["days_left"] == 41 and certs["cert-3"]["days_left"] == 3
    for cert in certs.values():
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", cert["not_after"])
    assert "sertifikat o'qilmadi" in proc.stderr and "broken" in proc.stderr


def test_status_json_backups(jctx: Ctx) -> None:
    root = jctx.base / "backups" / "Alpha"
    (root / "daily").mkdir(parents=True)
    (root / "weekly").mkdir()
    newest = time.time() - 3600
    for i, age in enumerate((3 * 86400, 2 * 86400, 0)):
        f = root / "daily" / f"Alpha-{i}.sql.gz"
        f.write_bytes(b"x")
        os.utime(f, (newest - age, newest - age))
    (root / "daily" / "Alpha-9.sql.gz.tmp").write_bytes(b"x")  # to'liq emas: hisobga olinmaydi
    for i in range(2):
        (root / "weekly" / f"Alpha-w{i}.sql.gz").write_bytes(b"x")
    (root / "weekly" / "Alpha-files-1.tar.gz").write_bytes(b"x")  # fayl zaxirasi weekly_count ga kirmaydi
    (jctx.base / "backups" / "Empty" / "daily").mkdir(parents=True)

    backups = by_name(as_json(jctx.run(NEW, "status", "--json"))["backups"], "project")
    assert set(backups) == {"Alpha", "Empty"}
    assert backups["Alpha"]["daily_count"] == 3 and backups["Alpha"]["weekly_count"] == 2
    got = datetime.fromisoformat(backups["Alpha"]["last_daily_at"].replace("Z", "+00:00"))
    assert abs(got - datetime.fromtimestamp(newest, UTC)).total_seconds() < 2
    assert backups["Empty"] == {
        "project": "Empty",
        "last_daily_at": None,
        "daily_count": 0,
        "weekly_count": 0,
    }


def test_status_json_degrades_gracefully(jctx: Ctx) -> None:
    proc = jctx.run(NEW, "status", "--json", FAKE_DOCKER_DOWN="1", FAKE_NO_DF="1")
    assert proc.returncode == 0
    data = as_json(proc)
    assert data["containers"] is None and data["disk"] is None  # "yo'q" emas, "bilib bo'lmadi"
    assert data["memory"]["total_bytes"] == 8321499136
    assert data["certificates"] == [] and data["backups"] == []


def test_status_json_never_contains_secrets(jctx: Ctx) -> None:
    containers = "web\\tUp 1 hour (password=hunter2 token=abc)\\n"
    proc = jctx.run(NEW, "status", "--json", FAKE_CONTAINERS=containers)
    assert "hunter2" not in proc.stdout and "token=***" in proc.stdout


# ---------------------------------------------------------------- xato JSON'i (TZ 18.1: {"schema":1,"error":...}, kod 1)
@pytest.mark.parametrize("cmd", ["list", "status"])
def test_broken_appctl_file_gives_error_json(jctx: Ctx, cmd: str) -> None:
    (jctx.base / "projects" / "Alpha" / ".appctl").write_text("DB_SERVICE=(\n")  # sintaksis xatosi
    proc = jctx.run(NEW, cmd, "--json")
    if cmd == "status":  # status Docker loyihalarini o'qimaydi, .appctl unga ta'sir qilmaydi
        assert proc.returncode == 0 and json.loads(proc.stdout)["schema"] == 1
        return
    assert proc.returncode == 1
    err = json.loads(proc.stdout)  # stdout bo'lsa ham yaroqli JSON
    assert err["schema"] == 1 and err["error"]
    assert set(err) == {"schema", "error"}


def test_human_mode_errors_stay_plain_text(jctx: Ctx) -> None:
    (jctx.base / "projects" / "Alpha" / ".appctl").write_text("DB_SERVICE=(\n")
    proc = jctx.run(NEW, "list")
    assert proc.returncode != 0 and not proc.stdout.lstrip().startswith("{")
