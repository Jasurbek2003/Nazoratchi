"""Agent o'z-o'zini yangilashi, core tomoni (FR-AGT-008, TZ 7.7.3, 14.5.4)."""

import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from apps.core import dist
from apps.registry.models import AgentToken, HostEvent, Server

from .conftest import make_batch
from .test_registry_crud import call, client_for

DIGEST = "ab" * 32
SUMS = (
    f"{DIGEST}  nazoratchi-agent-amd64\n{'cd' * 32}  nazoratchi-agent-arm64\n{'ef' * 32}  VERSION\n"
)


@pytest.fixture
def release(tmp_path: Path, settings: Any) -> Path:
    """Tarqatish papkasi: 1.2.0 relizi."""
    (tmp_path / "VERSION").write_text("1.2.0\n")
    (tmp_path / "SHA256SUMS").write_text(SUMS)
    settings.AGENT_DIST_DIR = str(tmp_path)
    return tmp_path


def host(version: str = "nazoratchi-agent/1.0.0", arch: str | None = "amd64") -> tuple[Server, str]:
    facts = {"arch": arch} if arch else {}
    server = Server.objects.create(name="main-2", agent_version=version, facts=facts)
    _, token = AgentToken.issue(server)
    return server, token


def send(token: str, version: str, facts: dict[str, Any] | None = None) -> Any:
    batch = make_batch([{"n": "cpu_busy_percent", "t": 1, "v": 1.0}])
    if facts:
        batch["facts"] = facts
    return Client().post(
        "/ingest/v1/metrics",
        data=gzip.compress(json.dumps(batch).encode()),
        content_type="application/json",
        headers={
            "Content-Encoding": "gzip",
            "Authorization": f"Bearer {token}",
            "X-Nazoratchi-Agent": f"nazoratchi-agent/{version}",
        },
    )


# ---- dist yordamchilari ----


def test_version_parsing_and_dist_helpers(release: Path) -> None:
    assert dist.parse_version("nazoratchi-agent/1.2.3") == (1, 2, 3)
    assert dist.parse_version("v2.0.10") == (2, 0, 10)
    for bad in ("", "dev", "1.2", "1.2.3-rc1", "nazoratchi-agent/", "1.2.3.4"):
        assert dist.parse_version(bad) is None, bad
    assert dist.latest_agent_version() == "1.2.0"
    assert dist.agent_binary_sha256("amd64") == DIGEST
    assert dist.agent_binary_sha256("riscv") is None
    assert dist.update_command("amd64") == {
        "type": "update",
        "version": "1.2.0",
        "sha256": DIGEST,
        "url": "/agent/v1/nazoratchi-agent-amd64",
    }


def test_dist_helpers_reject_missing_or_malformed(tmp_path: Path, settings: Any) -> None:
    settings.AGENT_DIST_DIR = str(tmp_path)
    assert dist.latest_agent_version() is None and dist.update_command("amd64") is None
    (tmp_path / "VERSION").write_text("1.2.0; rm -rf /\n")
    assert dist.latest_agent_version() is None
    (tmp_path / "VERSION").write_text("1.2.0\n")
    (tmp_path / "SHA256SUMS").write_text("NOTHEX  nazoratchi-agent-amd64\n")
    assert dist.agent_binary_sha256("amd64") is None and dist.update_command("amd64") is None


def test_version_file_is_served_and_unknown_names_are_not(release: Path) -> None:
    c = Client()
    response: Any = c.get("/agent/v1/VERSION")
    assert b"".join(response.streaming_content).strip() == b"1.2.0"
    assert c.get("/agent/v1/../etc/passwd").status_code == 404
    (release / "secret.txt").write_text("x")
    assert c.get("/agent/v1/secret.txt").status_code == 404


# ---- ingest buyrug'i ----


@pytest.mark.django_db
def test_no_command_unless_owner_requested(release: Path) -> None:
    _, token = host()
    assert send(token, "1.0.0").json()["commands"] == []


@pytest.mark.django_db
def test_update_command_sent_until_host_reaches_target(release: Path) -> None:
    server, token = host()
    Server.objects.filter(pk=server.pk).update(agent_update_to="1.2.0")

    cmds = send(token, "1.0.0").json()["commands"]
    assert cmds == [dist.update_command("amd64")]
    assert send(token, "1.0.0").json()["commands"] == cmds  # agent hali yangilanmadi: takrorlanadi

    # Agent 1.2.0 bilan keldi: so'rov tugaydi, buyruq yo'q, "yangilandi" voqeasi yoziladi
    assert send(token, "1.2.0").json()["commands"] == []
    server.refresh_from_db()
    assert server.agent_update_to == ""
    event = HostEvent.objects.get(server=server, type="agent_updated")
    assert event.data == {"from": "1.0.0", "to": "1.2.0", "requested": True}
    assert send(token, "1.2.0").json()["commands"] == []
    assert HostEvent.objects.filter(type="agent_updated").count() == 1  # takror voqea yo'q


@pytest.mark.django_db
def test_no_command_when_dist_already_not_newer_or_arch_unknown(release: Path) -> None:
    server, token = host(arch=None)  # fakt hali kelmagan
    Server.objects.filter(pk=server.pk).update(agent_update_to="1.2.0")
    assert send(token, "1.0.0").json()["commands"] == []

    Server.objects.filter(pk=server.pk).update(facts={"arch": "amd64"})
    (release / "VERSION").write_text("1.0.0\n")  # reliz papkasi o'zgarib, endi yangi emas
    assert send(token, "1.0.0").json()["commands"] == []


@pytest.mark.django_db
def test_rollback_is_recorded_as_downgrade(release: Path) -> None:
    server, token = host(version="nazoratchi-agent/1.2.0")
    send(token, "1.1.0")
    event = HostEvent.objects.get(server=server)
    assert (
        event.type == "agent_downgraded"
        and event.data["from"] == "1.2.0"
        and event.data["to"] == "1.1.0"
    )


# ---- API ----


@pytest.fixture
def owner() -> Client:
    return client_for("egasi", "owner")


def url(server: Server) -> str:
    return f"/api/v1/servers/{server.pk}/agent-update"


@pytest.mark.django_db
def test_only_owner_can_request_update(release: Path, owner: Client) -> None:
    server, _ = host()
    for role in ("operator", "viewer"):
        c = client_for(role, role)
        assert call(c, "post", url(server)).status_code == 403
        assert call(c, "delete", url(server)).status_code == 403
    anon = Client()
    assert anon.post(url(server), content_type="application/json").status_code in (401, 403)
    server.refresh_from_db()
    assert server.agent_update_to == ""


@pytest.mark.django_db
def test_request_and_cancel_update(release: Path, owner: Client) -> None:
    server, token = host()
    r = call(owner, "post", url(server))
    assert r.status_code == 202 and r.json()["agent_update_to"] == "1.2.0"
    assert HostEvent.objects.filter(
        server=server, type="agent_update_requested", data__to="1.2.0"
    ).exists()
    assert send(token, "1.0.0").json()["commands"] != []

    assert call(owner, "delete", url(server)).status_code == 200
    server.refresh_from_db()
    assert server.agent_update_to == ""
    assert HostEvent.objects.filter(server=server, type="agent_update_cancelled").exists()
    assert send(token, "1.0.0").json()["commands"] == []
    assert call(owner, "delete", url(server)).status_code == 409


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("version", "arch", "dist_version", "fragment"),
    [
        ("nazoratchi-agent/dev", "amd64", "1.2.0", "noma'lum"),
        ("", "amd64", "1.2.0", "noma'lum"),
        ("nazoratchi-agent/1.0.0", None, "1.2.0", "arxitektura"),
        ("nazoratchi-agent/1.0.0", "amd64", None, "reliz fayllari"),
        ("nazoratchi-agent/1.2.0", "amd64", "1.2.0", "eng yangi"),
        ("nazoratchi-agent/1.3.0", "amd64", "1.2.0", "eng yangi"),  # orqaga qaytarish so'ralmaydi
    ],
)
def test_request_update_conflicts(
    release: Path,
    owner: Client,
    version: str,
    arch: str | None,
    dist_version: str | None,
    fragment: str,
) -> None:
    if dist_version is None:
        (release / "VERSION").unlink()
    else:
        (release / "VERSION").write_text(dist_version + "\n")
    server, _ = host(version=version, arch=arch)
    r = call(owner, "post", url(server))
    assert r.status_code == 409 and fragment in r.json()["error"]["message"]
    server.refresh_from_db()
    assert server.agent_update_to == ""


@pytest.mark.django_db
def test_archived_or_missing_server_is_404(release: Path, owner: Client) -> None:
    server, _ = host()
    Server.objects.filter(pk=server.pk).update(status="archived")
    assert call(owner, "post", url(server)).status_code == 404
    missing = "/api/v1/servers/00000000-0000-0000-0000-000000000000/agent-update"
    assert call(owner, "post", missing).status_code == 404
