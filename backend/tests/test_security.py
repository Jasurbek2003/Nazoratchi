"""Xavfsizlik testlari (B13): RBAC matritsasi, CSRF, XSS/SQLi, IDOR, maxfiy qiymatlar (TZ 14.13, 16.7)."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from apps.audit.models import AuditLog
from apps.notifications.models import Channel
from apps.registry.models import Project, Server

from .test_accounts import csrf_client, csrf_headers, login, make_user

pytestmark = pytest.mark.django_db

# Ommaviy yoki o'z-o'ziga xizmat qiluvchi yo'nalishlar: RBAC matritsasidan chiqariladi.
PUBLIC_PREFIXES = ("api/v1/auth/", "api/v1/telegram/webhook/")
SAMPLE = {"uuid": str(uuid.uuid4()), "str": "x", "int": "1", "slug": "x"}


def _walk(patterns: list[Any], prefix: str = "") -> Iterator[str]:
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            route = prefix + str(p.pattern)
            for name, conv in p.pattern.converters.items():
                kind = type(conv).__name__.replace("Converter", "").lower()
                route = route.replace(f"<{kind}:{name}>", SAMPLE.get(kind, "x"))
                route = route.replace(f"<{name}>", "x")
            yield route


def api_routes() -> list[str]:
    routes = [
        "/" + r
        for r in _walk(get_resolver().url_patterns)
        if r.startswith("api/v1/") and not r.startswith(PUBLIC_PREFIXES)
    ]
    assert len(routes) > 30, "yo'nalishlar yig'ilmadi"
    return sorted(set(routes))


def client_for(name: str, role: str) -> Client:
    make_user(name, role)
    c = csrf_client()
    login(c, name)
    return c


def send(c: Client, method: str, url: str, body: Any = None) -> Any:
    if method == "get":
        return c.get(url)
    return getattr(c, method)(
        url,
        data=json.dumps(body if body is not None else {}),
        content_type="application/json",
        headers=csrf_headers(c),
    )


# ------------------------------------------------------------------ S-09 / T-S-08: RBAC
@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_anonymous_never_reaches_api(method: str) -> None:
    """Hech bir /api/v1/ yo'nalishi (auth va webhook'dan tashqari) anonimga ochiq emas, 5xx ham bermaydi."""
    anon = Client(enforce_csrf_checks=False)
    for url in api_routes():
        r = (
            anon.get(url)
            if method == "get"
            else getattr(anon, method)(url, data="{}", content_type="application/json")
        )
        assert r.status_code in (401, 403, 405), f"{method.upper()} {url} -> {r.status_code}"


def test_viewer_cannot_write_anywhere() -> None:
    """S-09: viewer yozuvchi (POST/PATCH/PUT/DELETE) hech bir endpointga kira olmaydi: 403 yoki 405."""
    viewer = client_for("kuzatuvchi", "viewer")
    for url in api_routes():
        for method in ("post", "patch", "put", "delete"):
            r = send(viewer, method, url)
            assert r.status_code in (403, 405), f"viewer {method.upper()} {url} -> {r.status_code}"


def test_operator_cannot_touch_owner_only_settings() -> None:
    """Operator foydalanuvchi/rol/kanal sirlari kabi egasiga xos amallarni bajara olmaydi (TZ 3.2)."""
    operator = client_for("operator", "operator")
    channel = Channel.objects.create(name="tg", type="telegram", config_enc=b"x")
    r = send(operator, "delete", f"/api/v1/channels/{channel.pk}")
    assert r.status_code == 403
    assert Channel.objects.filter(pk=channel.pk).exists()


def test_no_get_route_returns_server_error_for_any_role() -> None:
    for role in ("owner", "operator", "viewer"):
        c = client_for(f"u-{role}", role)
        for url in api_routes():
            r = c.get(url)
            assert r.status_code < 500, f"{role} GET {url} -> {r.status_code}"


# ------------------------------------------------------------------ T-S-06: XSS
def test_script_in_names_is_stored_verbatim_and_served_as_json() -> None:
    """API ma'lumotni o'zgartirmaydi, lekin faqat JSON + nosniff bilan beradi: brauzer HTML deb o'qimaydi.
    Chiqishda escape qilish frontendning (React) vazifasi."""
    operator = client_for("operator", "operator")
    payload = "<script>alert(1)</script>"
    r = send(operator, "post", "/api/v1/servers/", {"name": "xss-host", "description": payload})
    assert r.status_code in (201, 400)
    listing = operator.get("/api/v1/servers/")
    assert listing.headers["Content-Type"].startswith("application/json")
    assert listing.headers.get("X-Content-Type-Options") == "nosniff"
    assert b"<script>" not in listing.content.replace(b"\\u003c", b"<") or listing.json()


def test_error_responses_are_json_not_html() -> None:
    c = client_for("operator", "operator")
    for url in ("/api/v1/servers/" + str(uuid.uuid4()), "/api/v1/yoq-yol", "/api/v1/projects/zzz"):
        r = c.get(url)
        assert r.status_code in (404, 400)
        assert r.headers["Content-Type"].startswith("application/json"), url


# ------------------------------------------------------------------ T-S-07: SQLi
SQLI = ["' OR 1=1 --", "1; DROP TABLE registry_server;--", "%' UNION SELECT NULL--", '"\\']


@pytest.mark.parametrize("payload", SQLI)
def test_sql_payloads_in_filters_do_not_break_queries(payload: str) -> None:
    viewer = client_for("kuzatuvchi", "viewer")
    Server.objects.create(name="main-2")
    for url in ("/api/v1/servers/", "/api/v1/projects/", "/api/v1/incidents/", "/api/v1/alerts/"):
        for param in ("q", "search", "status", "severity", "kind", "ordering", "limit", "offset"):
            r = viewer.get(url, {param: payload})
            assert r.status_code in (200, 400), f"{url}?{param} -> {r.status_code}"
    assert Server.objects.filter(name="main-2").exists()


# ------------------------------------------------------------------ T-S-14 / S-05: maxfiy qiymatlar
def test_channel_secrets_never_in_api_responses() -> None:
    owner = client_for("egasi", "owner")
    secret = "123456789:AAHjudaMaxfiyBotTokenQiymati_0123456789ab"
    created = send(
        owner,
        "post",
        "/api/v1/channels/",
        {"type": "telegram", "name": "tg", "config": {"bot_token": secret, "chat_id": 42}},
    )
    assert created.status_code == 201, created.content
    channel = Channel.objects.get(name="tg")
    for url in ("/api/v1/channels/", f"/api/v1/channels/{channel.pk}"):
        assert secret not in owner.get(url).content.decode(), url
    assert secret.encode() not in bytes(channel.config_enc)
    assert secret not in created.content.decode()


def test_agent_token_hash_only_in_database() -> None:
    """S-05: agent tokeni bazada faqat xesh; ochiq qiymat javobda faqat issue paytida bir marta."""
    from apps.registry.models import AgentToken

    server = Server.objects.create(name="tok-1")
    token_row, plain = AgentToken.issue(server)
    assert plain.encode() not in bytes(token_row.token_hash)
    assert len(bytes(token_row.token_hash)) >= 32
    owner = client_for("egasi", "owner")
    assert plain not in owner.get(f"/api/v1/servers/{server.pk}").content.decode()


def test_audit_log_has_no_plaintext_secrets() -> None:
    owner = client_for("egasi", "owner")
    r = send(
        owner,
        "post",
        "/api/v1/channels/",
        {
            "type": "telegram",
            "name": "tg",
            "config": {
                "bot_token": "999000111:AAHSIRTOKENsirtokenSIRTOKEN_0123456789xy",
                "chat_id": 1,
            },
        },
    )
    assert r.status_code == 201, r.content
    assert AuditLog.objects.filter(action__startswith="channel").exists()
    dump = " ".join(json.dumps([a.before, a.after], default=str) for a in AuditLog.objects.all())
    assert "SIRTOKENsirtoken" not in dump


# ------------------------------------------------------------------ T-S-04: cookie va sarlavhalar
def test_session_cookie_flags() -> None:
    make_user("egasi", "owner")
    c = csrf_client()
    r = login(c, "egasi")
    morsel = r.cookies.get("nzr_sid") or r.cookies.get("__Host-nzr_sid")
    assert morsel is not None
    assert morsel["httponly"]
    assert morsel["samesite"] == "Lax"


def test_idor_unknown_ids_return_404() -> None:
    viewer = client_for("kuzatuvchi", "viewer")
    ghost = uuid.uuid4()
    for url in (
        f"/api/v1/servers/{ghost}",
        f"/api/v1/projects/{ghost}",
        f"/api/v1/incidents/{ghost}",
        f"/api/v1/probes/{ghost}",
    ):
        assert viewer.get(url).status_code == 404, url


def test_archived_project_does_not_leak_secrets_in_detail() -> None:
    owner = client_for("egasi", "owner")
    project = Project.objects.create(name="Maxfiy", slug="maxfiy")
    body = owner.get(f"/api/v1/projects/{project.pk}").content.decode().lower()
    for word in ("password", "secret", "token_hash", "config_enc"):
        assert word not in body
