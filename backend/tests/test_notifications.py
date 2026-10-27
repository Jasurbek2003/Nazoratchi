"""Bildirishnomalar: shifrlash, Telegram klienti, xabar shabloni, qayta urinish, API (FR-NTF-001..004, 14.6)."""

import json
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.crypto import DecryptionError, decrypt_json, encrypt_json
from apps.core.logging import mask_secrets
from apps.notifications import services, telegram
from apps.notifications.messages import MAX_LEN, Message, render
from apps.notifications.models import Channel, Notification

from .test_accounts import csrf_client, csrf_headers, login, make_user

pytestmark = pytest.mark.django_db

BOT_TOKEN = "123456789:AAH-secretTOKENsecretTOKENsecret_abcd12"
CHAT = -1001234567890


# ---------------------------------------------------------------- yordamchilar
class FakeTelegram:
    """`httpx.MockTransport` orqali Telegram Bot API ni taqlid qiladi."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.requests: list[httpx.Request] = []
        self.script: list[Callable[[httpx.Request], httpx.Response]] = []
        monkeypatch.setattr(
            telegram,
            "make_client",
            lambda: httpx.Client(transport=httpx.MockTransport(self._handle)),
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.script:
            return self.script.pop(0)(request)
        return ok_response(request)

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]


def ok_response(request: httpx.Request, message_id: int = 77) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": {"message_id": message_id}})


def fail(status: int, description: str = "xato", **extra: Any) -> Callable[..., httpx.Response]:
    return lambda request: httpx.Response(
        status, json={"ok": False, "description": description, **extra}
    )


def make_channel(
    name: str = "asosiy", min_severity: str = "warning", enabled: bool = True
) -> Channel:
    channel = Channel(
        type=Channel.Type.TELEGRAM, name=name, min_severity=min_severity, enabled=enabled
    )
    channel.set_config({"bot_token": BOT_TOKEN, "chat_id": CHAT})
    channel.save()
    return channel


@pytest.fixture
def tg(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    return FakeTelegram(monkeypatch)


@pytest.fixture
def owner() -> Client:
    make_user("egasi", "owner")
    client = csrf_client()
    login(client, "egasi")
    return client


@pytest.fixture
def operator() -> Client:
    make_user("operator", "operator")
    client = csrf_client()
    login(client, "operator")
    return client


def api(client: Client, method: str, url: str, body: Any = None) -> Any:
    return getattr(client, method)(
        url,
        data=json.dumps(body) if body is not None else None,
        content_type="application/json",
        headers=csrf_headers(client),
    )


# ---------------------------------------------------------------- shifrlash
def test_encrypt_roundtrip_and_fresh_nonce() -> None:
    a, b = encrypt_json({"x": 1}, b"aad"), encrypt_json({"x": 1}, b"aad")
    assert a != b  # har yozuv uchun yangi nonce
    assert decrypt_json(a, b"aad") == {"x": 1}


def test_decrypt_rejects_wrong_aad_tampering_and_short_input() -> None:
    blob = encrypt_json({"x": 1}, b"kanal-1")
    with pytest.raises(DecryptionError):
        decrypt_json(blob, b"kanal-2")  # boshqa qatorga ko'chirilgan
    tampered = bytearray(blob)
    tampered[-1] ^= 1
    with pytest.raises(DecryptionError):
        decrypt_json(bytes(tampered), b"kanal-1")
    with pytest.raises(DecryptionError):
        decrypt_json(b"short", b"kanal-1")


def test_channel_secret_is_encrypted_at_rest_and_bound_to_its_id() -> None:
    channel = make_channel()
    raw = bytes(Channel.objects.get(pk=channel.pk).config_enc)
    assert BOT_TOKEN.encode() not in raw and b"bot_token" not in raw
    assert Channel.objects.get(pk=channel.pk).get_config() == {
        "bot_token": BOT_TOKEN,
        "chat_id": CHAT,
    }
    other = make_channel("boshqa")
    other.config_enc = channel.config_enc  # shifrlangan sirni boshqa kanalga ko'chirish
    with pytest.raises(DecryptionError):
        other.get_config()


def test_master_key_validation() -> None:
    from django.core.exceptions import ImproperlyConfigured

    from config.settings.base import master_key

    with pytest.raises(ImproperlyConfigured):
        master_key("bu-base64-emas!")
    with pytest.raises(ImproperlyConfigured):
        master_key("YWJj")  # 3 bayt
    assert len(master_key("ZGV2LWtleS1mYXFhdC1pc2hsYWItY2hpcWlzaC0wMDA=")) == 32


# ---------------------------------------------------------------- xabar shabloni
def test_render_escapes_html_and_adds_button() -> None:
    out = render(
        Message(
            severity="critical",
            title="Server <o'chdi>: main-2",
            lines=["TCP:22 — javob yo'q & ICMP", "<script>x</script>"],
            runbook="RB-001 → <tekshiring>",
            path="/incidents/0193",
        )
    )
    text = out["text"]
    assert text.startswith("🔴 <b>Server &lt;o'chdi&gt;: main-2</b>")
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert "Nima qilish kerak: RB-001 → &lt;tekshiring&gt;" in text
    assert text.endswith("Incident: http://127.0.0.1:8000/incidents/0193")
    assert out["buttons"] == [
        {"text": "Panelda ochish", "url": "http://127.0.0.1:8000/incidents/0193"}
    ]


def test_render_respects_limit_and_keeps_head_and_tail() -> None:
    out = render(
        Message(
            severity="high",
            title="T" * 400,
            lines=["x" * 300 for _ in range(10)],
            runbook="RB-009",
            path="/incidents/1",
        )
    )
    text = out["text"]
    assert len(text) <= MAX_LEN
    assert text.count("<b>") == 1 and text.count("</b>") == 1  # teglar buzilmagan
    assert "Nima qilish kerak: RB-009" in text and text.endswith("/incidents/1")


def test_render_resolved_icon_and_no_link() -> None:
    out = render(Message(severity="critical", title="Tiklandi", resolved=True))
    assert out["text"].startswith("✅") and out["buttons"] == []


# ---------------------------------------------------------------- Telegram klienti
def test_send_message_posts_html_with_buttons(tg: FakeTelegram) -> None:
    sent = telegram.send_message(BOT_TOKEN, CHAT, "salom", [{"text": "Ochish", "url": "https://x"}])
    assert sent.message_id == "77"
    request = tg.requests[0]
    assert request.url.path == f"/bot{BOT_TOKEN}/sendMessage"
    body = tg.bodies()[0]
    assert body["chat_id"] == CHAT and body["parse_mode"] == "HTML"
    assert body["reply_markup"] == {"inline_keyboard": [[{"text": "Ochish", "url": "https://x"}]]}


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (401, False), (403, False), (500, True), (502, True)]
)
def test_send_message_classifies_errors(tg: FakeTelegram, status: int, retryable: bool) -> None:
    tg.script = [fail(status, "Forbidden: bot was blocked by the user")]
    with pytest.raises(telegram.TelegramError) as info:
        telegram.send_message(BOT_TOKEN, CHAT, "x")
    assert info.value.retryable is retryable and str(status) in str(info.value)


def test_send_message_429_carries_retry_after(tg: FakeTelegram) -> None:
    tg.script = [fail(429, "Too Many Requests", parameters={"retry_after": 17})]
    with pytest.raises(telegram.TelegramError) as info:
        telegram.send_message(BOT_TOKEN, CHAT, "x")
    assert info.value.retryable and info.value.retry_after == 17


def test_errors_never_contain_bot_token(tg: FakeTelegram, monkeypatch: pytest.MonkeyPatch) -> None:
    tg.script = [fail(400, f"Bad Request: token {BOT_TOKEN} is wrong")]
    with pytest.raises(telegram.TelegramError) as info:
        telegram.send_message(BOT_TOKEN, CHAT, "x")
    assert BOT_TOKEN not in str(info.value)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connect failed for {request.url}")

    monkeypatch.setattr(
        telegram, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(boom))
    )
    with pytest.raises(telegram.TelegramError) as net:
        telegram.send_message(BOT_TOKEN, CHAT, "x")
    assert net.value.retryable and BOT_TOKEN not in str(net.value)
    assert BOT_TOKEN not in repr(net.value.__cause__) and net.value.__suppress_context__


def test_log_masking_covers_bot_url() -> None:
    line = f"POST https://api.telegram.org/bot{BOT_TOKEN}/sendMessage 200"
    assert BOT_TOKEN not in mask_secrets(line)
    assert "/bot***/sendMessage" in mask_secrets(line)


def test_httpx_logger_is_quiet_by_default() -> None:
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


# ---------------------------------------------------------------- servis: navbat va qayta urinish
def test_enqueue_filters_by_severity_and_enabled() -> None:
    crit = make_channel("faqat-critical", min_severity="critical")
    warn = make_channel("warning+", min_severity="warning")
    make_channel("o'chiq", enabled=False)
    rows = services.enqueue(Message(severity="high", title="x"), event="opened")
    assert {r.channel_id for r in rows} == {warn.id}
    rows = services.enqueue(Message(severity="critical", title="x"), event="opened")
    assert {r.channel_id for r in rows} == {crit.id, warn.id}
    assert services.enqueue(Message(severity="info", title="x"), event="opened") == []


def test_deliver_success_records_message_id_and_channel_health(tg: FakeTelegram) -> None:
    channel = make_channel()
    channel.last_error = "eski xato"
    channel.save()
    (n,) = services.enqueue(Message(severity="critical", title="Server o'chdi"), event="opened")
    assert services.deliver_due() == 1
    n.refresh_from_db()
    channel.refresh_from_db()
    assert (n.status, n.attempts, n.external_id) == ("sent", 1, "77") and n.sent_at is not None
    assert channel.last_ok_at is not None and channel.last_error == ""
    assert "Server o'chdi" in tg.bodies()[0]["text"]
    assert services.deliver_due() == 0  # qayta yuborilmaydi


def test_transient_failure_retries_with_backoff_then_succeeds(tg: FakeTelegram) -> None:
    channel = make_channel()
    tg.script = [fail(502), fail(500)]
    (n,) = services.enqueue(Message(severity="critical", title="x"), event="opened")
    t0 = timezone.now()

    assert services.deliver_due(now=t0) == 1
    n.refresh_from_db()
    assert (n.status, n.attempts) == ("queued", 1)
    assert n.next_attempt_at == t0 + timedelta(seconds=services.RETRY_DELAYS_S[0])
    assert services.deliver_due(now=t0 + timedelta(seconds=1)) == 0  # hali erta

    t1 = t0 + timedelta(seconds=6)
    assert services.deliver_due(now=t1) == 1
    n.refresh_from_db()
    assert n.attempts == 2 and n.next_attempt_at == t1 + timedelta(
        seconds=services.RETRY_DELAYS_S[1]
    )
    channel.refresh_from_db()
    assert "500" in channel.last_error  # panelda kanal ishlamayotgani ko'rinadi

    assert services.deliver_due(now=t1 + timedelta(seconds=16)) == 1
    n.refresh_from_db()
    channel.refresh_from_db()
    assert (n.status, n.attempts, n.error) == ("sent", 3, "") and channel.last_error == ""


def test_gives_up_after_five_attempts(tg: FakeTelegram) -> None:
    make_channel()
    tg.script = [fail(500) for _ in range(10)]
    (n,) = services.enqueue(Message(severity="critical", title="x"), event="opened")
    now = timezone.now()
    for _ in range(10):
        services.deliver_due(now=now)
        now += timedelta(hours=1)
    n.refresh_from_db()
    assert (n.status, n.attempts) == ("failed", services.MAX_ATTEMPTS)
    assert len(tg.requests) == services.MAX_ATTEMPTS


def test_permanent_error_is_not_retried(tg: FakeTelegram) -> None:
    channel = make_channel()
    tg.script = [fail(403, "Forbidden: bot was blocked by the user")]
    (n,) = services.enqueue(Message(severity="critical", title="x"), event="opened")
    services.deliver_due()
    n.refresh_from_db()
    channel.refresh_from_db()
    assert (n.status, n.attempts) == ("failed", 1)
    assert "blocked" in n.error and "blocked" in channel.last_error


def test_rate_limit_honours_retry_after(tg: FakeTelegram) -> None:
    make_channel()
    tg.script = [fail(429, "Too Many Requests", parameters={"retry_after": 40})]
    (n,) = services.enqueue(Message(severity="critical", title="x"), event="opened")
    t0 = timezone.now()
    services.deliver_due(now=t0)
    n.refresh_from_db()
    assert n.status == "queued" and n.next_attempt_at == t0 + timedelta(seconds=40)


def test_due_notifications_are_sent_oldest_first(tg: FakeTelegram) -> None:
    make_channel()
    now = timezone.now()
    for title, offset in (("ikkinchi", 1), ("birinchi", 5)):
        (n,) = services.enqueue(Message(severity="critical", title=title), event="opened")
        Notification.objects.filter(pk=n.pk).update(next_attempt_at=now - timedelta(seconds=offset))
    assert services.deliver_due(now=now) == 2
    assert [b["text"].split("</b>")[0][-8:] for b in tg.bodies()] == ["birinchi", "ikkinchi"]


def test_unreadable_channel_config_fails_without_retry(tg: FakeTelegram) -> None:
    channel = make_channel()
    Channel.objects.filter(pk=channel.pk).update(config_enc=b"x" * 40)  # kalit almashgan/buzilgan
    (n,) = services.enqueue(Message(severity="critical", title="x"), event="opened")
    services.deliver_due()
    n.refresh_from_db()
    assert n.status == "failed" and "shifrni ochib bo'lmadi" in n.error and not tg.requests


def test_unsupported_channel_type_fails() -> None:
    channel = Channel(type=Channel.Type.EMAIL, name="pochta")
    channel.set_config({})
    channel.save()
    (n,) = services.enqueue(
        Message(severity="critical", title="x"), event="opened", channels=[channel]
    )
    services.deliver_due()
    n.refresh_from_db()
    assert n.status == "failed" and "qo'llab-quvvatlanmaydi" in n.error


def test_send_test_is_single_attempt(tg: FakeTelegram) -> None:
    channel = make_channel()
    tg.script = [fail(500)]
    n = services.send_test(channel)
    assert (n.status, n.attempts, n.event) == ("failed", 1, "test")  # sinovda qayta urinish yo'q
    n = services.send_test(channel)
    assert n.status == "sent" and "sinov xabari" in tg.bodies()[-1]["text"]


# ---------------------------------------------------------------- API
def create_channel(client: Client, **extra: Any) -> Any:
    body = {
        "type": "telegram",
        "name": "asosiy",
        "config": {"bot_token": BOT_TOKEN, "chat_id": CHAT},
        **extra,
    }
    return api(client, "post", "/api/v1/channels/", body)


def test_create_channel_masks_secret_everywhere(owner: Client) -> None:
    response = create_channel(owner, min_severity="high")
    assert response.status_code == 201
    body = response.json()
    assert body["config_masked"] == {"bot_token": "••••", "chat_id": CHAT}
    assert "config" not in body and BOT_TOKEN not in response.content.decode()
    listing = owner.get("/api/v1/channels/")
    assert (
        BOT_TOKEN not in listing.content.decode()
        and listing.json()["items"][0]["min_severity"] == "high"
    )
    assert BOT_TOKEN not in str(list(AuditLog.objects.values()))
    assert AuditLog.objects.filter(action="channel.create", object_id=body["id"]).exists()
    assert BOT_TOKEN.encode() not in bytes(Channel.objects.get().config_enc)


@pytest.mark.parametrize(
    ("config", "field_hint"),
    [
        ({"bot_token": "123", "chat_id": CHAT}, "bot_token"),
        ({"bot_token": BOT_TOKEN, "chat_id": "abc"}, "chat_id"),
        ({"bot_token": BOT_TOKEN, "chat_id": True}, "chat_id"),
        ({"bot_token": BOT_TOKEN}, "chat_id"),
        ({"bot_token": BOT_TOKEN, "chat_id": CHAT, "extra": 1}, "extra"),
    ],
)
def test_create_channel_validates_config(
    owner: Client, config: dict[str, Any], field_hint: str
) -> None:
    response = create_channel(owner, config=config)
    assert response.status_code == 400
    assert field_hint in json.dumps(response.json()["error"]["details"])
    assert Channel.objects.count() == 0


def test_create_channel_validation_misc(owner: Client) -> None:
    assert create_channel(owner, type="email").status_code == 400  # F2
    assert create_channel(owner, min_severity="zo'r").status_code == 400
    assert (
        api(owner, "post", "/api/v1/channels/", {"type": "telegram", "name": "x"}).status_code
        == 400
    )
    assert (
        create_channel(owner, config={"bot_token": BOT_TOKEN, "chat_id": "@kanal_nomi"}).status_code
        == 201
    )
    dup = create_channel(owner, config={"bot_token": BOT_TOKEN, "chat_id": "@kanal_nomi"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate"


def test_patch_merges_config_and_audits_without_secrets(owner: Client) -> None:
    channel_id = create_channel(owner).json()["id"]
    response = api(
        owner, "patch", f"/api/v1/channels/{channel_id}",
        {"config": {"chat_id": -100999}, "enabled": False, "min_severity": "critical"},
    )  # fmt: skip
    assert response.status_code == 200
    assert (
        response.json()["config_masked"]["chat_id"] == -100999
        and response.json()["enabled"] is False
    )
    assert Channel.objects.get().get_config() == {
        "bot_token": BOT_TOKEN,
        "chat_id": -100999,
    }  # token saqlandi
    assert (
        api(owner, "patch", f"/api/v1/channels/{channel_id}", {"type": "webhook"}).status_code
        == 400
    )
    assert (
        api(
            owner, "patch", f"/api/v1/channels/{channel_id}", {"config": {"bot_token": "yomon"}}
        ).status_code
        == 400
    )
    entry = AuditLog.objects.get(action="channel.update")
    assert entry.before is not None and entry.after is not None
    assert entry.before["enabled"] is True and entry.after["enabled"] is False
    assert BOT_TOKEN not in str(list(AuditLog.objects.values()))


def test_delete_channel(owner: Client) -> None:
    channel_id = create_channel(owner).json()["id"]
    assert api(owner, "delete", f"/api/v1/channels/{channel_id}").status_code == 204
    assert (
        Channel.objects.count() == 0 and AuditLog.objects.filter(action="channel.delete").exists()
    )
    missing = api(owner, "delete", f"/api/v1/channels/{channel_id}")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_channels_are_owner_only(owner: Client, operator: Client) -> None:
    channel_id = create_channel(owner).json()["id"]
    assert operator.get("/api/v1/channels/").status_code == 403
    assert create_channel(operator, name="x").status_code == 403
    assert (
        api(operator, "patch", f"/api/v1/channels/{channel_id}", {"enabled": False}).status_code
        == 403
    )
    assert api(operator, "delete", f"/api/v1/channels/{channel_id}").status_code == 403
    assert api(operator, "post", f"/api/v1/channels/{channel_id}/test").status_code == 403
    assert Client().get("/api/v1/channels/").status_code in (401, 403)


def test_channel_test_endpoint(owner: Client, tg: FakeTelegram) -> None:
    channel_id = create_channel(owner).json()["id"]
    ok = api(owner, "post", f"/api/v1/channels/{channel_id}/test")
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert Channel.objects.get().last_ok_at is not None
    tg.script = [fail(403, "Forbidden: bot was blocked by the user")]
    bad = api(owner, "post", f"/api/v1/channels/{channel_id}/test")
    assert bad.status_code == 502 and "blocked" in bad.json()["error"]
    assert "blocked" in Channel.objects.get().last_error
    assert BOT_TOKEN not in bad.content.decode()
    assert (
        api(owner, "post", "/api/v1/channels/00000000-0000-7000-8000-000000000000/test").status_code
        == 404
    )


def test_notification_history_for_operator_with_filters_and_paging(
    owner: Client, operator: Client, tg: FakeTelegram
) -> None:
    channel = make_channel()
    for i in range(55):
        Notification.objects.create(
            channel=channel, event="opened", status="sent" if i % 2 else "failed"
        )
    first = operator.get("/api/v1/notifications/").json()
    assert len(first["items"]) == 50 and first["next_before"] is not None
    assert first["items"][0]["id"] > first["items"][-1]["id"]
    second = operator.get(f"/api/v1/notifications/?before={first['next_before']}").json()
    assert len(second["items"]) == 5 and second["next_before"] is None
    failed = operator.get("/api/v1/notifications/?status=failed").json()["items"]
    assert failed and all(i["status"] == "failed" and i["channel_name"] == "asosiy" for i in failed)
    assert operator.get("/api/v1/notifications/?before=abc").status_code == 400
    viewer = csrf_client()
    make_user("kuzatuvchi", "viewer")
    login(viewer, "kuzatuvchi")
    assert viewer.get("/api/v1/notifications/").status_code == 403
    assert "payload" not in json.dumps(first)  # xabar matni va sirlar tarixda qaytmaydi


# ---------------------------------------------------------------- buyruqlar
def test_notify_worker_once(tg: FakeTelegram) -> None:
    make_channel()
    (n,) = services.enqueue(Message(severity="critical", title="x"), event="opened")
    call_command("notify_worker", once=True)
    n.refresh_from_db()
    assert n.status == "sent"


def test_create_telegram_channel_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAZORATCHI_TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    call_command("create_telegram_channel", "asosiy", chat_id="-1001234567890", min_severity="high")
    channel = Channel.objects.get()
    assert channel.get_config() == {"bot_token": BOT_TOKEN, "chat_id": -1001234567890}
    assert channel.min_severity == "high"
    assert BOT_TOKEN not in str(list(AuditLog.objects.values()))
    with pytest.raises(CommandError, match="mavjud"):
        call_command("create_telegram_channel", "asosiy", chat_id="1")
    monkeypatch.setenv("NAZORATCHI_TELEGRAM_BOT_TOKEN", "yomon")
    with pytest.raises(CommandError, match="bot_token"):
        call_command("create_telegram_channel", "boshqa", chat_id="1")


def test_send_message_over_real_http_socket(settings: Any) -> None:
    """MockTransport'siz: haqiqiy httpx, haqiqiy TCP (URL yo'li, JSON tana, javobni o'qish)."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            payload = json.dumps({"ok": True, "result": {"message_id": 4242}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings.TELEGRAM_API_BASE = f"http://127.0.0.1:{server.server_port}"
        sent = telegram.send_message(BOT_TOKEN, CHAT, "salom")
    finally:
        server.shutdown()
    assert sent.message_id == "4242"
    assert seen["path"] == f"/bot{BOT_TOKEN}/sendMessage" and seen["body"]["text"] == "salom"
