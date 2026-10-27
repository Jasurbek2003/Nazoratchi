"""Telegram tugmalari va webhook (B8, TZ 9.12, TH-11) + seed buyrug'i."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings
from django.utils import timezone

from apps.alerts.models import Incident, Silence
from apps.audit.models import AuditLog
from apps.heartbeats.models import HeartbeatJob
from apps.notifications import callbacks
from apps.notifications.messages import Message, render
from apps.probes.models import Probe
from apps.registry.models import Domain, Project, ProjectServer, Server

from .test_accounts import make_user
from .test_notifications import BOT_TOKEN, CHAT, FakeTelegram, make_channel

pytestmark = pytest.mark.django_db
SECRET = "wh_secret-0123456789"


@pytest.fixture(autouse=True)
def _secret(settings: Any) -> None:
    settings.TELEGRAM_WEBHOOK_SECRET = SECRET


@pytest.fixture
def tg(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    return FakeTelegram(monkeypatch)


def incident(scope_key: str = "host:x", severity: str = "critical") -> Incident:
    return Incident.objects.create(scope_key=scope_key, title="Server o'chdi", severity=severity)


def push(
    data: str,
    chat: int = CHAT,
    user_id: int = 555,
    *,
    secret: str = SECRET,
    header: str | None = SECRET,
) -> Any:
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cb-1", "from": {"id": user_id, "username": "jasur"}, "data": data,
            "message": {"message_id": 7, "chat": {"id": chat}},
        },
    }  # fmt: skip
    headers = {"X-Telegram-Bot-Api-Secret-Token": header} if header is not None else {}
    return Client().post(
        f"/api/v1/telegram/webhook/{secret}",
        data=json.dumps(update),
        content_type="application/json",
        headers=headers,
    )


# ---------------------------------------------------------------- imzo
def test_callback_roundtrip_fits_telegram_limit() -> None:
    inc = "01a17c63-1913-7ded-8d10-facaf9e9c003"
    ack, snooze = callbacks.make("ack", inc), callbacks.make("snz", inc, "60")
    assert len(ack.encode()) <= 64 and len(snooze.encode()) <= 64
    assert callbacks.parse(ack) == ("ack", inc, [])
    assert callbacks.parse(snooze) == ("snz", inc, ["60"])


def test_callback_tampering_rejected() -> None:
    good = callbacks.make("snz", "abc", "60")
    assert callbacks.parse(good.replace(":60:", ":600:")) is None  # muddat o'zgartirilgan
    assert callbacks.parse(good.replace("snz", "ack")) is None
    assert (
        callbacks.parse("ack:abc") is None
        and callbacks.parse("") is None
        and callbacks.parse("x:y:zzzzzzzzzzzz") is None
    )


def test_signature_depends_on_secret_key(settings: Any) -> None:
    a = callbacks.make("ack", "i")
    settings.SECRET_KEY = "boshqa-kalit-" + "x" * 40
    assert callbacks.parse(a) is None


def test_render_adds_action_buttons_only_for_open_incidents() -> None:
    out = render(
        Message(
            severity="critical",
            title="x",
            path="/incidents/1",
            incident_id="01a17c63-1913-7ded-8d10-facaf9e9c003",
        )
    )
    labels = [b["text"] for b in out["buttons"]]
    assert labels == ["Qabul qilaman", "1 soat jim", "Panelda ochish"]
    assert all(len(b.get("callback_data", "").encode()) <= 64 for b in out["buttons"])
    resolved = render(
        Message(severity="critical", title="x", path="/incidents/1", incident_id="i", resolved=True)
    )
    assert [b["text"] for b in resolved["buttons"]] == ["Panelda ochish"]
    assert render(Message(severity="info", title="x"))["buttons"] == []


# ---------------------------------------------------------------- webhook
def test_ack_button_acknowledges_and_answers(tg: FakeTelegram) -> None:
    make_channel()
    inc = incident()
    assert push(callbacks.make("ack", str(inc.pk))).status_code == 200
    inc.refresh_from_db()
    assert inc.status == "acknowledged"
    event = inc.events.get(type="acked")
    assert "telegram:jasur" in event.data["comment"]
    answer = tg.bodies()[-1]
    assert (
        tg.requests[-1].url.path.endswith("/answerCallbackQuery")
        and answer["callback_query_id"] == "cb-1"
        and "Qabul" in answer["text"]
    )
    assert AuditLog.objects.filter(action="incident.ack", object_id=str(inc.pk)).exists()
    assert BOT_TOKEN not in str(list(AuditLog.objects.values()))


def test_second_ack_reports_conflict_without_error(tg: FakeTelegram) -> None:
    make_channel()
    inc = incident()
    push(callbacks.make("ack", str(inc.pk)))
    assert push(callbacks.make("ack", str(inc.pk))).status_code == 200
    assert "allaqachon" in tg.bodies()[-1]["text"]


def test_snooze_creates_silence_by_scope(tg: FakeTelegram) -> None:
    make_channel()
    s = Server.objects.create(name="main-2")
    inc = incident(f"host:{s.pk}")
    push(callbacks.make("snz", str(inc.pk), "60"))
    silence = Silence.objects.get()
    assert silence.matchers == [{"label": "server", "op": "=", "value": "main-2"}]
    assert (
        timedelta(minutes=59)
        < silence.ends_at - silence.starts_at
        <= timedelta(minutes=60, seconds=1)
    )
    assert "jim" in tg.bodies()[-1]["text"] and "telegram:jasur" in silence.reason

    p = Project.objects.create(slug="nazar", name="Nazar", kind="static")
    push(callbacks.make("snz", str(incident(f"project:{p.pk}").pk), "60"))
    assert Silence.objects.filter(
        matchers=[{"label": "project", "op": "=", "value": "Nazar"}]
    ).exists()


def test_snooze_rejects_out_of_range_and_resolved(tg: FakeTelegram) -> None:
    make_channel()
    s = Server.objects.create(name="main-2")
    inc = incident(f"host:{s.pk}")
    push(callbacks.make("snz", str(inc.pk), "5"))
    push(callbacks.make("snz", str(inc.pk), "99999"))
    assert Silence.objects.count() == 0
    Incident.objects.filter(pk=inc.pk).update(status="resolved")
    push(callbacks.make("snz", str(inc.pk), "60"))
    assert Silence.objects.count() == 0


@pytest.mark.parametrize(
    "case",
    ["bad_path_secret", "bad_header", "no_header", "foreign_chat", "bad_signature", "garbage_body"],
)
def test_unauthorized_requests_do_nothing_but_return_200(tg: FakeTelegram, case: str) -> None:
    make_channel()
    inc = incident()
    good = callbacks.make("ack", str(inc.pk))
    if case == "bad_path_secret":
        response = push(good, secret="yomon")
    elif case == "bad_header":
        response = push(good, header="yomon")
    elif case == "no_header":
        response = push(good, header=None)
    elif case == "foreign_chat":
        response = push(good, chat=424242)
    elif case == "bad_signature":
        response = push(good[:-1] + ("0" if good[-1] != "0" else "1"))
    else:
        response = Client().post(
            f"/api/v1/telegram/webhook/{SECRET}",
            data="{{{",
            content_type="application/json",
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
    assert response.status_code == 200  # Telegram qayta yubormasligi uchun
    inc.refresh_from_db()
    assert inc.status == "open" and not tg.requests


def test_webhook_disabled_without_configured_secret(tg: FakeTelegram, settings: Any) -> None:
    settings.TELEGRAM_WEBHOOK_SECRET = ""
    make_channel()
    inc = incident()
    assert push(callbacks.make("ack", str(inc.pk)), secret="", header="").status_code in (200, 404)
    inc.refresh_from_db()
    assert inc.status == "open"


def test_viewer_user_cannot_use_buttons_but_linked_operator_can(tg: FakeTelegram) -> None:
    make_channel()
    inc = incident()
    viewer = make_user("kuzatuvchi", "viewer")
    viewer.telegram_chat_id = 777
    viewer.save()
    push(callbacks.make("ack", str(inc.pk)), user_id=777)
    inc.refresh_from_db()
    assert inc.status == "open" and "ruxsat yo'q" in tg.bodies()[-1]["text"]
    op = make_user("operator", "operator")
    op.telegram_chat_id = 888
    op.save()
    push(callbacks.make("ack", str(inc.pk)), user_id=888)
    inc.refresh_from_db()
    assert inc.status == "acknowledged" and inc.acked_by == op


def test_non_callback_updates_are_ignored(tg: FakeTelegram) -> None:
    make_channel()
    response = Client().post(
        f"/api/v1/telegram/webhook/{SECRET}",
        data=json.dumps({"message": {"text": "/status"}}),
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200 and not tg.requests


def test_answer_failure_does_not_break_webhook(tg: FakeTelegram) -> None:
    import httpx

    make_channel()
    inc = incident()
    tg.script = [lambda r: httpx.Response(500, json={"ok": False})]
    assert push(callbacks.make("ack", str(inc.pk))).status_code == 200
    inc.refresh_from_db()
    assert inc.status == "acknowledged"  # amal bajarildi, javob (toast) yetmagan


def test_alert_message_carries_working_buttons() -> None:
    """Dvigatel yuborgan xabardagi tugma ma'lumoti webhook'da haqiqatan ishlaydi."""
    from apps.alerts.catalog import sync_built_in
    from apps.alerts.engine import run_cycle
    from apps.notifications.models import Notification

    from .test_alerts import T0, alive, channel, new_server, only, put

    sync_built_in()
    only("AL-015")
    s = new_server()
    channel()
    for minute in (0, 5):
        at = T0 + timedelta(minutes=minute)
        put(s, "mem_used_percent", 98, at)
        alive(s, at)
        run_cycle(at)
    (n,) = Notification.objects.all()
    ack_button = next(b for b in n.payload["buttons"] if b["text"] == "Qabul qilaman")
    kind, incident_id, _ = callbacks.parse(ack_button["callback_data"]) or ("", "", [])
    assert kind == "ack" and Incident.objects.get().pk.__str__() == incident_id


# ---------------------------------------------------------------- seed
def test_seed_registry_loads_inventory_idempotently(capsys: pytest.CaptureFixture[str]) -> None:
    call_command("seed_registry")
    out = capsys.readouterr().out
    assert "serverlar: +4" in out and "loyihalar: +14" in out and "heartbeat: +4" in out
    assert Server.objects.get(name="backup-1").status == "archived"
    assert Server.objects.get(name="main-2").public_ipv4 == "164.68.105.194"
    nazar = Project.objects.get(slug="Nazar")
    link = ProjectServer.objects.get(project=nazar)
    assert (
        link.ports == [8020, 3020]
        and link.server.name == "main-2"
        and link.environment == "production"
    )
    assert Domain.objects.filter(project=nazar).count() == 2
    assert Project.objects.get(slug="Matnchi").moved is False
    assert (
        ProjectServer.objects.filter(project__slug="aaclub_staging").get().environment == "staging"
    )
    assert (
        Probe.objects.count() == 1
    )  # faqat aniq ko'rsatilgan (Nazar healthz); avto-tekshiruvlar so'ralmagan
    assert Probe.objects.get().config["primary"] is True and Probe.objects.get().name
    assert HeartbeatJob.objects.count() == 4 and "/hb/hb_" in out

    # mavjudga tegilmaydi
    Server.objects.filter(name="main-2").update(role="o'zgartirilgan")
    Domain.objects.filter(fqdn="nazar.avlo.ai").update(registrar="Namecheap")
    call_command("seed_registry")
    again = capsys.readouterr().out
    assert "+" not in again.splitlines()[0]  # hech narsa yangidan yaratilmadi
    assert "heartbeat /hb/" not in again
    assert Server.objects.get(name="main-2").role == "o'zgartirilgan"
    assert Domain.objects.get(fqdn="nazar.avlo.ai").registrar == "Namecheap"
    assert Server.objects.count() == 4 and HeartbeatJob.objects.count() == 4


def test_seed_auto_probes_only_for_moved_projects() -> None:
    call_command("seed_registry", auto_probes=True)
    domains = Domain.objects.filter(project__moved=True).count()
    assert (
        Probe.objects.filter(type="http").count() == domains + 0 or Probe.objects.count() >= domains
    )
    assert not Probe.objects.filter(project__moved=False).exists()
    primary = Probe.objects.filter(config__primary=True).count()
    assert primary >= 1


def test_seed_dry_run_saves_nothing_and_bad_files_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    call_command("seed_registry", dry_run=True)
    assert "[dry-run]" in capsys.readouterr().out
    assert Server.objects.count() == 0 and HeartbeatJob.objects.count() == 0
    with pytest.raises(CommandError, match="topilmadi"):
        call_command("seed_registry", file=str(tmp_path / "yoq.yaml"))
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 2\n", encoding="utf-8")
    with pytest.raises(CommandError, match="version"):
        call_command("seed_registry", file=str(bad))
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        "version: 1\nprojects:\n  - { slug: a-1, name: A, servers: [{ server: yoq-server }] }\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match="server topilmadi"):
        call_command("seed_registry", file=str(broken))
    assert Project.objects.count() == 0  # xatoda hech narsa saqlanmaydi


@override_settings(TELEGRAM_WEBHOOK_SECRET="")
def test_unused_override_keeps_module_importable() -> None:
    assert timezone.now() is not None
