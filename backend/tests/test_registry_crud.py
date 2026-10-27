"""Reyestr CRUD (B2): serverlar, loyihalar, domenlar, port to'qnashuvi, arxiv (FR-REG-001..006, 010; FR-HST-016)."""

import json
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.alerts.engine import run_cycle
from apps.alerts.models import Incident
from apps.audit.models import AuditLog
from apps.probes.models import Probe
from apps.registry.models import AgentToken, Domain, HostEvent, Project, ProjectServer, Server

from .test_accounts import csrf_client, csrf_headers, login, make_user

pytestmark = pytest.mark.django_db


def client_for(name: str, role: str) -> Client:
    make_user(name, role)
    c = csrf_client()
    login(c, name)
    return c


@pytest.fixture
def owner() -> Client:
    return client_for("egasi", "owner")


@pytest.fixture
def operator() -> Client:
    return client_for("operator", "operator")


@pytest.fixture
def viewer() -> Client:
    return client_for("kuzatuvchi", "viewer")


def call(c: Client, method: str, url: str, body: Any = None) -> Any:
    return getattr(c, method)(
        url,
        data=json.dumps(body) if body is not None else None,
        content_type="application/json",
        headers=csrf_headers(c),
    )


def server(name: str = "main-2", **kw: Any) -> Server:
    return Server.objects.create(name=name, public_ipv4=kw.pop("ip", "164.68.105.194"), **kw)


# ---------------------------------------------------------------- serverlar
def test_server_list_filters(viewer: Client) -> None:
    server("main-2", tags=["docker", "prod"], provider="Contabo")
    server("core-1", ip="185.214.135.9", tags=["core"], status="paused")
    server("old-1", ip="1.1.1.1", status="archived")

    def names(url: str) -> list[str]:
        return [s["name"] for s in viewer.get(url).json()["items"]]

    assert names("/api/v1/servers/") == ["core-1", "main-2"]  # arxivlangan yashirin
    assert names("/api/v1/servers/?tag=docker") == ["main-2"]
    assert names("/api/v1/servers/?status=paused") == ["core-1"]
    assert names("/api/v1/servers/?status=archived") == ["old-1"]
    assert names("/api/v1/servers/?q=conta") == ["main-2"]
    assert names("/api/v1/servers/?q=185.214") == ["core-1"]


def test_server_patch_audited_and_validated(operator: Client, viewer: Client) -> None:
    s = server()
    other = server("core-1", ip="185.214.135.9")
    ok = call(
        operator,
        "patch",
        f"/api/v1/servers/{s.pk}",
        {"role": "production", "tags": ["a"], "notes": "x"},
    )
    assert ok.status_code == 200 and ok.json()["role"] == "production"
    entry = AuditLog.objects.get(action="server.update")
    assert entry.before is not None and entry.after is not None and entry.after["tags"] == ["a"]
    assert (
        call(operator, "patch", f"/api/v1/servers/{s.pk}", {"name": other.name}).status_code == 409
    )
    assert (
        call(operator, "patch", f"/api/v1/servers/{s.pk}", {"public_ipv4": "999.1.1.1"}).status_code
        == 400
    )
    assert (
        call(operator, "patch", f"/api/v1/servers/{s.pk}", {"status": "online"}).status_code == 200
    )
    s.refresh_from_db()
    assert s.status == "new"  # status faqat tizim tomonidan o'zgaradi
    assert call(viewer, "patch", f"/api/v1/servers/{s.pk}", {"role": "x"}).status_code == 403
    assert (
        call(
            operator, "patch", "/api/v1/servers/00000000-0000-7000-8000-000000000000", {}
        ).status_code
        == 404
    )


def test_server_detail_counts_open_incidents(viewer: Client) -> None:
    s = server()
    Incident.objects.create(scope_key=f"host:{s.pk}", title="t", severity="high")
    Incident.objects.create(
        scope_key=f"host:{s.pk}", title="eski", severity="high", status="resolved"
    )
    assert viewer.get(f"/api/v1/servers/{s.pk}").json()["open_incidents"] == 1


def test_pause_resume_flow(operator: Client, viewer: Client) -> None:
    s = server(last_seen_at=timezone.now(), status="online")
    base = f"/api/v1/servers/{s.pk}"
    assert call(operator, "post", f"{base}/pause", {}).status_code == 400  # sabab majburiy
    assert (
        call(
            operator, "post", f"{base}/pause", {"reason": "x", "until": "2020-01-01T00:00:00Z"}
        ).status_code
        == 400
    )
    far = (timezone.now() + timedelta(days=200)).isoformat()
    assert call(operator, "post", f"{base}/pause", {"reason": "x", "until": far}).status_code == 400
    assert call(viewer, "post", f"{base}/pause", {"reason": "x"}).status_code == 403
    paused = call(operator, "post", f"{base}/pause", {"reason": "kernel yangilash"})
    assert (
        paused.status_code == 200
        and paused.json()["status"] == "paused"
        and paused.json()["pause_reason"] == "kernel yangilash"
    )
    assert call(operator, "post", f"{base}/pause", {"reason": "yana"}).status_code == 409
    assert HostEvent.objects.filter(server=s, type="paused").exists()
    resumed = call(operator, "post", f"{base}/resume")
    assert (
        resumed.status_code == 200
        and resumed.json()["status"] == "online"
        and resumed.json()["pause_reason"] == ""
    )
    assert call(operator, "post", f"{base}/resume").status_code == 409


def test_pause_until_expires_by_itself() -> None:
    s = server(last_seen_at=timezone.now(), status="paused")
    Server.objects.filter(pk=s.pk).update(
        paused_until=timezone.now() - timedelta(minutes=1),
        pause_reason="x",
        paused_at=timezone.now(),
    )
    run_cycle(timezone.now())
    s.refresh_from_db()
    assert s.status == "online" and s.paused_until is None
    assert HostEvent.objects.filter(server=s, type="resumed").exists()


def test_archive_revokes_tokens_and_is_owner_only(owner: Client, operator: Client) -> None:
    s = server()
    AgentToken.issue(s)
    assert call(operator, "post", f"/api/v1/servers/{s.pk}/archive").status_code == 403
    done = call(owner, "post", f"/api/v1/servers/{s.pk}/archive")
    assert done.status_code == 200 and done.json()["status"] == "archived"
    assert AgentToken.objects.get().revoked_at is not None
    assert HostEvent.objects.filter(server=s, type="archived").exists()
    assert call(owner, "post", f"/api/v1/servers/{s.pk}/archive").status_code == 404  # allaqachon
    assert [x["name"] for x in owner.get("/api/v1/servers/").json()["items"]] == []


def test_events_and_tokens(owner: Client, operator: Client) -> None:
    s = server()
    _, secret = AgentToken.issue(s)
    for i in range(55):
        HostEvent.objects.create(server=s, type=f"e{i}")
    first = operator.get(f"/api/v1/servers/{s.pk}/events").json()
    assert len(first["items"]) == 50 and first["next_before"]
    rest = operator.get(f"/api/v1/servers/{s.pk}/events?before={first['next_before']}").json()
    assert len(rest["items"]) == 5 and rest["next_before"] is None
    assert operator.get(f"/api/v1/servers/{s.pk}/events?before=x").status_code == 400

    assert operator.get(f"/api/v1/servers/{s.pk}/tokens").status_code == 403
    listing = owner.get(f"/api/v1/servers/{s.pk}/tokens")
    body = listing.content.decode()
    assert listing.status_code == 200 and secret not in body and "token_hash" not in body
    token_id = listing.json()["items"][0]["id"]
    assert call(operator, "delete", f"/api/v1/servers/{s.pk}/tokens/{token_id}").status_code == 403
    assert call(owner, "delete", f"/api/v1/servers/{s.pk}/tokens/{token_id}").status_code == 204
    assert call(owner, "delete", f"/api/v1/servers/{s.pk}/tokens/{token_id}").status_code == 404
    assert AuditLog.objects.filter(action="token.revoke").exists()


# ---------------------------------------------------------------- loyihalar
def make_project(c: Client, **extra: Any) -> Any:
    body = {"slug": "Nazar", "name": "Nazar (Beyondlinks)", "kind": "compose", **extra}
    return call(c, "post", "/api/v1/projects/", body)


def test_create_project_with_servers_domains_and_auto_probes(operator: Client) -> None:
    s = server()
    response = make_project(
        operator,
        servers=[{"server_id": str(s.pk), "environment": "production", "ports": [8020, 3020]}],
        domains=[{"fqdn": "Nazar.AVLO.ai."}, {"fqdn": "app.beyondlinks.uz", "dns_provider": "x"}],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["servers_info"][0] == {
        "server_id": str(s.pk),
        "server": "main-2",
        "environment": "production",
        "ports": [8020, 3020],
    }
    assert [d["fqdn"] for d in body["domains_info"]] == [
        "app.beyondlinks.uz",
        "nazar.avlo.ai",
    ]  # kichik harf, nuqtasiz
    probes = Probe.objects.filter(type="http")
    assert Probe.objects.filter(type="tls").count() == 2  # har domen uchun TLS ham
    assert probes.count() == 2 and {p.config["url"] for p in probes} == {
        "https://nazar.avlo.ai/",
        "https://app.beyondlinks.uz/",
    }
    assert AuditLog.objects.filter(action="project.create").exists()


def test_create_project_without_auto_probes_and_moved_false(operator: Client) -> None:
    make_project(operator, slug="a-1", domains=[{"fqdn": "a.example.uz"}], auto_probes=False)
    make_project(
        operator, slug="b-1", moved=False, domains=[{"fqdn": "b.example.uz"}]
    )  # ko'chirilmagan: tekshiruvsiz
    assert Probe.objects.count() == 0 and Domain.objects.count() == 2


def test_project_validation_and_duplicates(operator: Client, viewer: Client) -> None:
    assert make_project(operator).status_code == 201
    dup = make_project(operator)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate"
    assert make_project(operator, slug="bad slug").status_code == 400
    assert make_project(operator, slug="x-1", kind="nomalum").status_code == 400
    assert make_project(operator, slug="x-2", domains=[{"fqdn": "not a domain"}]).status_code == 400
    assert (
        make_project(
            operator, slug="x-3", servers=[{"server_id": "00000000-0000-7000-8000-000000000000"}]
        ).status_code
        == 400
    )
    assert make_project(viewer, slug="x-4").status_code == 403
    assert Project.objects.count() == 1  # xato bo'lganlar qoldiq qoldirmadi


def test_duplicate_domain_rolls_back_whole_project(operator: Client) -> None:
    make_project(operator, slug="a-1", domains=[{"fqdn": "same.example.uz"}])
    response = make_project(operator, slug="b-1", domains=[{"fqdn": "same.example.uz"}])
    assert response.status_code == 409
    assert not Project.objects.filter(slug="b-1").exists()


def test_port_conflict_with_suggestion(operator: Client) -> None:
    s = server()

    def link(slug: str, ports: list[int]) -> Any:
        return make_project(operator, slug=slug, servers=[{"server_id": str(s.pk), "ports": ports}])

    assert link("nazar", [8020, 3020]).status_code == 201
    clash = link("biznes", [8020])
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "port_conflict"
    detail = clash.json()["error"]["details"][0]
    assert (
        detail["code"] == "port_in_use"
        and "'nazar'" in detail["message"]
        and "[8000, 3000]" in detail["message"]
    )
    assert link("biznes", [8030, 8030]).status_code == 409  # ro'yxat ichida takror
    assert not Project.objects.filter(slug="biznes").exists()
    assert link("biznes", [80]).status_code == 400  # 1024 dan past


def test_next_ports_skip_used_and_archived_free_them(operator: Client, owner: Client) -> None:
    s = server()

    def nxt() -> list[int]:
        return list(operator.get(f"/api/v1/projects/ports/next?server_id={s.pk}").json()["ports"])

    assert nxt() == [8000, 3000]
    project = make_project(
        operator, servers=[{"server_id": str(s.pk), "ports": [8000, 3000]}]
    ).json()
    assert nxt() == [8001, 3001]
    make_project(operator, slug="q-1", servers=[{"server_id": str(s.pk), "ports": [8001, 3500]}])
    assert nxt() == [8002, 3002]
    call(owner, "post", f"/api/v1/projects/{project['id']}/archive")
    assert nxt() == [8000, 3000]  # arxivlangan loyiha portni bo'shatadi
    assert operator.get("/api/v1/projects/ports/next?server_id=xato").status_code == 400
    assert operator.get("/api/v1/projects/ports/next").status_code == 400


def test_put_servers_replaces_and_checks_other_projects(operator: Client) -> None:
    a, b = server("a-1", ip="1.1.1.1"), server("b-1", ip="2.2.2.2")
    p1 = make_project(
        operator, slug="p-1", servers=[{"server_id": str(a.pk), "ports": [8020]}]
    ).json()
    p2 = make_project(
        operator, slug="p-2", servers=[{"server_id": str(a.pk), "ports": [8030]}]
    ).json()
    same = call(
        operator,
        "put",
        f"/api/v1/projects/{p1['id']}/servers",
        [{"server_id": str(a.pk), "ports": [8020, 8021]}],
    )
    assert same.status_code == 200  # o'z portlari to'qnashuv emas
    clash = call(
        operator,
        "put",
        f"/api/v1/projects/{p2['id']}/servers",
        [{"server_id": str(a.pk), "ports": [8021]}],
    )
    assert clash.status_code == 409
    moved = call(
        operator,
        "put",
        f"/api/v1/projects/{p2['id']}/servers",
        [{"server_id": str(b.pk), "environment": "staging", "ports": [8021]}],
    )
    assert moved.status_code == 200 and moved.json()["servers"][0]["server"] == "b-1"
    assert ProjectServer.objects.filter(project_id=p2["id"]).count() == 1  # almashtirildi
    dup = call(
        operator,
        "put",
        f"/api/v1/projects/{p2['id']}/servers",
        [{"server_id": str(a.pk)}, {"server_id": str(a.pk)}],
    )
    assert dup.status_code == 400
    assert AuditLog.objects.filter(action="project.servers").count() == 2


def test_project_list_detail_patch_archive(operator: Client, owner: Client, viewer: Client) -> None:
    s = server()
    p = make_project(
        operator,
        slug="nazar",
        tags=["django"],
        domains=[{"fqdn": "nazar.avlo.ai"}],
        servers=[{"server_id": str(s.pk)}],
        auto_probes=False,
    ).json()
    make_project(operator, slug="eski", name="Eski", moved=False)

    def items(q: str = "") -> list[str]:
        return [x["slug"] for x in viewer.get(f"/api/v1/projects/{q}").json()["items"]]

    assert items() == ["eski", "nazar"]
    assert (
        items("?q=avlo") == ["nazar"]
        and items("?tag=django") == ["nazar"]
        and items("?moved=false") == ["eski"]
    )
    assert items(f"?server_id={s.pk}") == ["nazar"]
    assert viewer.get(f"/api/v1/projects/{p['id']}").json()["slug"] == "nazar"
    patched = call(
        operator,
        "patch",
        f"/api/v1/projects/{p['id']}",
        {"name": "Yangi nom", "slug": "o'zgartirilmaydi", "notes": "n"},
    )
    assert (
        patched.status_code == 200
        and patched.json()["name"] == "Yangi nom"
        and patched.json()["slug"] == "nazar"
    )
    assert call(viewer, "patch", f"/api/v1/projects/{p['id']}", {"name": "x"}).status_code == 403
    probe = Probe.objects.create(
        project_id=p["id"], type="http", name="t", config={"url": "https://nazar.avlo.ai/"}
    )
    assert call(operator, "post", f"/api/v1/projects/{p['id']}/archive").status_code == 403
    assert call(owner, "post", f"/api/v1/projects/{p['id']}/archive").status_code == 200
    probe.refresh_from_db()
    assert probe.enabled is False  # arxivlangan alert yubormaydi
    assert items() == ["eski"] and items("?status=archived") == ["nazar"]
    assert call(operator, "patch", f"/api/v1/projects/{p['id']}", {"name": "x"}).status_code == 404


# ---------------------------------------------------------------- domenlar
def test_domain_crud_and_normalization(operator: Client, viewer: Client) -> None:
    p = make_project(operator, auto_probes=False).json()
    created = call(
        operator,
        "post",
        "/api/v1/domains/",
        {"fqdn": " WWW.Example.UZ. ", "project": p["id"], "expected_ips": ["164.68.105.194"]},
    )
    assert created.status_code == 201 and created.json()["fqdn"] == "www.example.uz"
    assert Probe.objects.filter(type="http").count() == 1  # auto_probes standart
    assert call(operator, "post", "/api/v1/domains/", {"fqdn": "www.example.uz"}).status_code == 409
    for bad in ("localhost", "1.2.3.4", "a..b.uz", "-a.example.uz", "a b.uz", "x" * 64 + ".uz"):
        assert call(operator, "post", "/api/v1/domains/", {"fqdn": bad}).status_code == 400, bad
    assert (
        call(
            operator,
            "post",
            "/api/v1/domains/",
            {"fqdn": "ok.example.uz", "expected_ips": ["yomon"]},
        ).status_code
        == 400
    )
    assert call(viewer, "post", "/api/v1/domains/", {"fqdn": "v.example.uz"}).status_code == 403
    domain_id = created.json()["id"]
    assert viewer.get(f"/api/v1/domains/{domain_id}").json()["project_slug"] == "Nazar"
    assert [
        d["fqdn"] for d in viewer.get(f"/api/v1/domains/?project_id={p['id']}").json()["items"]
    ] == ["www.example.uz"]
    assert [d["fqdn"] for d in viewer.get("/api/v1/domains/?q=WWW").json()["items"]] == [
        "www.example.uz"
    ]
    assert (
        call(operator, "patch", f"/api/v1/domains/{domain_id}", {"registrar": "Namecheap"}).json()[
            "registrar"
        ]
        == "Namecheap"
    )
    call(operator, "post", "/api/v1/domains/", {"fqdn": "second.example.uz", "auto_probes": False})
    assert (
        call(
            operator, "patch", f"/api/v1/domains/{domain_id}", {"fqdn": "second.example.uz"}
        ).status_code
        == 409
    )


def test_domain_without_project_or_unmoved_gets_no_probe_and_archive_disables(
    operator: Client,
) -> None:
    call(operator, "post", "/api/v1/domains/", {"fqdn": "free.example.uz"})
    moved_false = make_project(operator, slug="m-1", moved=False).json()
    call(
        operator, "post", "/api/v1/domains/", {"fqdn": "m.example.uz", "project": moved_false["id"]}
    )
    assert Probe.objects.count() == 0
    p = make_project(operator, slug="live").json()
    d = call(
        operator, "post", "/api/v1/domains/", {"fqdn": "live.example.uz", "project": p["id"]}
    ).json()
    assert Probe.objects.filter(enabled=True).count() == 2  # HTTP + TLS
    call(operator, "patch", f"/api/v1/domains/{d['id']}", {"status": "archived"})
    assert not Probe.objects.filter(enabled=True).exists()
    assert [x["fqdn"] for x in operator.get("/api/v1/domains/").json()["items"]] == [
        "free.example.uz",
        "m.example.uz",
    ]
