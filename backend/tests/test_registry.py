"""Serverlar, enroll oqimi, goodbye va ingest tezlik chegarasi (TZ 9.3, 7.5.1, FR-AGT-002, NFR-SEC-007)."""

import time
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registry.models import AgentToken, EnrollToken, HostEvent, Server, hash_token

from .conftest import make_batch, post_batch
from .test_accounts import csrf_client, csrf_headers, login, make_user

pytestmark = pytest.mark.django_db


def create_server(client: Client, name: str = "main-2", **extra: Any) -> Any:
    return client.post(
        "/api/v1/servers/",
        {"name": name, **extra},
        content_type="application/json",
        headers=csrf_headers(client),
    )


@pytest.fixture
def operator() -> Client:
    make_user("operator", "operator")
    client = csrf_client()
    login(client, "operator")
    return client


@pytest.fixture
def owner() -> Client:
    make_user("egasi", "owner")
    client = csrf_client()
    login(client, "egasi")
    return client


def enroll(client: Client, token: str, **extra: Any) -> Any:
    return client.post(
        "/ingest/v1/enroll",
        {"enroll_token": token, "hostname": "vmi3679093", "agent_version": "1.0.0", **extra},
        content_type="application/json",
    )


# ---------------------------------------------------------------- serverlar API
def test_create_server_returns_enroll_command_and_audits(operator: Client) -> None:
    response = create_server(
        operator, provider="Contabo", public_ipv4="164.68.105.194", tags=["contabo"]
    )
    assert response.status_code == 201
    body = response.json()
    assert (
        body["name"] == "main-2"
        and body["status"] == "new"
        and body["public_ipv4"] == "164.68.105.194"
    )
    enroll_info = body["enroll"]
    assert enroll_info["token"].startswith("enr_")
    assert enroll_info["install_command"].endswith(f"--token {enroll_info['token']}")
    assert "/install.sh" in enroll_info["install_command"]
    assert AuditLog.objects.filter(action="server.create", object_id=body["id"]).exists()
    # Token ochiq holda saqlanmaydi (audit va baza)
    assert enroll_info["token"] not in str(list(AuditLog.objects.values()))
    row = EnrollToken.objects.get()
    assert bytes(row.token_hash) == hash_token(enroll_info["token"])
    assert timedelta(minutes=59) < row.expires_at - timezone.now() <= timedelta(hours=1)


def test_create_server_validation_and_duplicates(operator: Client) -> None:
    assert create_server(operator).status_code == 201
    duplicate = create_server(operator)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "duplicate"
    bad = create_server(operator, name="x")  # juda qisqa
    assert bad.status_code == 400 and bad.json()["error"]["details"][0]["field"] == "name"
    assert create_server(operator, name="yaxshi nom").status_code == 400  # bo'shliq
    assert create_server(operator, name="ok-1", public_ipv4="999.1.1.1").status_code == 400
    assert Server.objects.count() == 1


def test_list_and_detail_hide_archived_and_unknown(operator: Client) -> None:
    created = create_server(operator).json()
    create_server(operator, name="eski-srv")
    Server.objects.filter(name="eski-srv").update(status="archived")
    names = [s["name"] for s in operator.get("/api/v1/servers/").json()["items"]]
    assert names == ["main-2"]
    assert operator.get(f"/api/v1/servers/{created['id']}").json()["name"] == "main-2"
    missing = operator.get("/api/v1/servers/00000000-0000-7000-8000-000000000000")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    assert Client().get("/api/v1/servers/").status_code in (401, 403)


def test_enroll_token_endpoint_is_owner_only(owner: Client, operator: Client) -> None:
    server_id = create_server(owner).json()["id"]
    assert (
        operator.post(
            f"/api/v1/servers/{server_id}/enroll-token",
            content_type="application/json",
            headers=csrf_headers(operator),
        ).status_code
        == 403
    )
    response = owner.post(
        f"/api/v1/servers/{server_id}/enroll-token",
        content_type="application/json",
        headers=csrf_headers(owner),
    )
    assert response.status_code == 201 and response.json()["token"].startswith("enr_")
    assert EnrollToken.objects.filter(server_id=server_id).count() == 2
    assert HostEvent.objects.filter(server_id=server_id, type="enroll_token_issued").exists()


# ---------------------------------------------------------------- enroll oqimi
def test_full_enroll_then_ingest_flow(operator: Client) -> None:
    token = create_server(operator).json()["enroll"]["token"]
    agent = Client()
    response = enroll(agent, token, facts={"os": "Ubuntu 24.04", "cpu_count": 4})
    assert response.status_code == 200
    data = response.json()
    assert data["agent_token"].startswith("agt_") and data["interval_seconds"] == 15
    server = Server.objects.get()
    assert str(server.id) == data["host_id"]
    assert server.facts["os"] == "Ubuntu 24.04" and server.facts["hostname"] == "vmi3679093"
    assert server.agent_version == "1.0.0" and server.status == "new"
    assert HostEvent.objects.filter(server=server, type="enrolled").exists()
    assert AuditLog.objects.filter(action="agent.enroll").exists()
    assert data["agent_token"] not in str(list(AuditLog.objects.values()))

    batch = make_batch([{"n": "cpu_busy_percent", "t": int(time.time() * 1000), "v": 5.0, "l": {}}])
    ingest = post_batch(agent, data["agent_token"], batch)
    assert ingest.status_code == 200 and ingest.json()["accepted"] == 1
    server.refresh_from_db()
    assert server.status == "online" and server.last_seen_at is not None


def test_enroll_token_is_single_use_and_expires(operator: Client) -> None:
    token = create_server(operator).json()["enroll"]["token"]
    assert enroll(Client(), token).status_code == 200
    again = enroll(Client(), token)
    assert again.status_code == 409 and again.json()["error"]["code"] == "host_already_enrolled"

    other = create_server(operator, name="srv-2").json()["enroll"]["token"]
    EnrollToken.objects.filter(token_hash=hash_token(other)).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    expired = enroll(Client(), other)
    assert expired.status_code == 410 and expired.json()["error"]["code"] == "enroll_token_expired"
    assert AgentToken.objects.filter(server__name="srv-2").count() == 0


@pytest.mark.parametrize("token", ["enr_yoq-token", "", "agt_boshqa-turdagi"])
def test_enroll_with_unknown_token_is_401(token: str) -> None:
    response = enroll(Client(), token)
    assert (
        response.status_code == 401 and response.json()["error"]["code"] == "invalid_enroll_token"
    )


def test_enroll_validates_body() -> None:
    client = Client()
    assert (
        client.post("/ingest/v1/enroll", b"{buzuq", content_type="application/json").status_code
        == 400
    )
    assert (
        client.post(
            "/ingest/v1/enroll", {"enroll_token": 5}, content_type="application/json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/ingest/v1/enroll",
            {"enroll_token": "enr_x", "facts": "yo'q"},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert client.get("/ingest/v1/enroll").status_code == 405


def test_enroll_is_rate_limited_per_ip() -> None:
    client = Client()
    codes = [enroll(client, f"enr_noto'g'ri{i}").status_code for i in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


# ---------------------------------------------------------------- goodbye
def test_goodbye_archives_host_and_revokes_tokens() -> None:
    server = Server.objects.create(name="main-2")
    _, token = AgentToken.issue(server)
    client = Client()
    response = client.post("/ingest/v1/goodbye", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    server.refresh_from_db()
    assert server.status == "archived"
    assert HostEvent.objects.filter(server=server, type="goodbye").exists()
    after = post_batch(client, token, make_batch([]))
    assert after.status_code == 401 and after.json()["error"]["code"] == "token_revoked"
    assert client.post("/ingest/v1/goodbye").status_code == 401


# ---------------------------------------------------------------- ingest holati va tezlik chegarasi
def test_paused_server_stays_paused_when_data_arrives(
    agent: tuple[Server, str], client: Client
) -> None:
    server, token = agent
    Server.objects.filter(pk=server.pk).update(status="paused")
    post_batch(
        client, token, make_batch([{"n": "load1", "t": int(time.time() * 1000), "v": 1.0, "l": {}}])
    )
    server.refresh_from_db()
    assert server.status == "paused" and server.last_seen_at is not None


def test_ingest_records_token_last_used_ip(agent: tuple[Server, str], client: Client) -> None:
    _, token = agent
    post_batch(client, token, make_batch([]))
    row = AgentToken.objects.get()
    assert row.last_used_ip == "127.0.0.1" and row.last_used_at is not None


def test_ingest_rate_limit_30_per_minute(agent: tuple[Server, str], client: Client) -> None:
    _, token = agent
    codes = [
        post_batch(client, token, make_batch([], batch_id=f"b-{i}")).status_code for i in range(32)
    ]
    assert codes[:30] == [200] * 30
    assert codes[30:] == [429, 429]
    limited = post_batch(client, token, make_batch([]))
    assert limited.json()["error"]["code"] == "rate_limited" and int(limited["Retry-After"]) > 0


def test_ingest_rate_limit_is_per_token(client: Client) -> None:
    tokens = []
    for name in ("srv-a", "srv-b"):
        server = Server.objects.create(name=name)
        tokens.append(AgentToken.issue(server)[1])
    for _ in range(30):
        post_batch(client, tokens[0], make_batch([]))
    assert post_batch(client, tokens[0], make_batch([])).status_code == 429
    assert post_batch(client, tokens[1], make_batch([])).status_code == 200


def test_ingest_survives_cache_failure(
    agent: tuple[Server, str], client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-C-02: Redis o'chsa ham ingest ishlaydi (tezlik chegarasi fail-open)."""
    from django.core.cache import cache

    def broken(*args: object, **kwargs: object) -> Any:
        raise ConnectionError("redis o'chiq")

    monkeypatch.setattr(cache, "add", broken)
    monkeypatch.setattr(cache, "incr", broken)
    _, token = agent
    assert post_batch(client, token, make_batch([])).status_code == 200
