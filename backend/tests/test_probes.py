"""Prober (B6): tekshiruvlar, SSRF filtri, tasdiqlash qoidasi, API, alertlar (TZ 6.8, 18.4; AL-049, AL-085)."""

import json
import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.alerts.catalog import sync_built_in
from apps.alerts.engine import run_cycle
from apps.alerts.models import AlertInstance, Incident
from apps.notifications.models import Notification
from apps.probes import checks, services
from apps.probes.models import Probe
from apps.registry.models import Domain, Project, ProjectServer, Server

from .test_accounts import csrf_client, csrf_headers, login, make_user
from .test_alerts import channel

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- mahalliy HTTP server
class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        routes: dict[str, tuple[int, dict[str, str], bytes]] = {
            "/ok": (200, {}, b"hello nazoratchi ok"),
            "/bad": (503, {}, b"down"),
            "/redir": (302, {"Location": "/ok"}, b""),
            "/loop": (302, {"Location": "/loop"}, b""),
            "/to-private": (302, {"Location": "http://internal.test/secret"}, b""),
            "/created": (201, {}, b"made"),
        }
        if self.path == "/slow":
            time.sleep(3)
        status, headers, body = routes.get(self.path, (200, {}, b"slow done"))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_HEAD = do_GET  # noqa: N815

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def web() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def http(url: str, **extra: Any) -> dict[str, Any]:
    return {"url": url, "allow_private": True, **extra}


# ---------------------------------------------------------------- HTTP tekshiruv
def test_http_ok_records_timings(web: str) -> None:
    out = checks.check_http(http(f"{web}/ok"), 5)
    assert out.ok and out.status_code == 200 and out.error_kind is None
    assert (
        out.total_ms is not None
        and out.dns_ms is not None
        and out.connect_ms is not None
        and out.ttfb_ms is not None
    )


def test_http_status_expectations(web: str) -> None:
    bad = checks.check_http(http(f"{web}/bad"), 5)
    assert not bad.ok and bad.error_kind == "status" and bad.status_code == 503
    assert checks.check_http(http(f"{web}/created", expected_status=[200, 201]), 5).ok
    assert checks.check_http(http(f"{web}/created", expected_status=["200-299"]), 5).ok
    assert not checks.check_http(http(f"{web}/created", expected_status=[200]), 5).ok


def test_http_keyword_modes(web: str) -> None:
    assert checks.check_http(
        http(f"{web}/ok", keyword={"text": "nazoratchi", "mode": "contains"}), 5
    ).ok
    miss = checks.check_http(http(f"{web}/ok", keyword={"text": "yo'q-so'z"}), 5)
    assert not miss.ok and miss.error_kind == "keyword"
    assert checks.check_http(
        http(f"{web}/ok", keyword={"text": "Error", "mode": "not_contains"}), 5
    ).ok
    assert not checks.check_http(
        http(f"{web}/ok", keyword={"text": "hello", "mode": "not_contains"}), 5
    ).ok


def test_http_redirects(web: str) -> None:
    assert checks.check_http(http(f"{web}/redir"), 5).ok
    nofollow = checks.check_http(
        http(f"{web}/redir", follow_redirects=False, expected_status=[302]), 5
    )
    assert nofollow.ok and nofollow.status_code == 302
    loop = checks.check_http(http(f"{web}/loop", max_redirects=3), 5)
    assert not loop.ok and loop.error_kind == "redirect_loop"


def closed_port() -> int:
    """Hozir hech kim tinglamayotgan port (ephemeral band qilinib, yopiladi)."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_http_timeout_and_connection_refused(web: str) -> None:
    slow = checks.check_http(http(f"{web}/slow"), 1)
    assert not slow.ok and slow.error_kind == "timeout"
    refused = checks.check_http(
        http(f"http://127.0.0.1:{closed_port()}/"), 6
    )  # Windows yopiq portda ~2 s kutadi
    assert not refused.ok and refused.error_kind == "connect"


def test_http_dns_failure() -> None:
    out = checks.check_http({"url": "http://no-such-host.invalid/", "allow_private": True}, 3)
    assert not out.ok and out.error_kind == "dns"


# ---------------------------------------------------------------- SSRF
def test_ssrf_blocks_loopback_private_and_metadata_by_default(web: str) -> None:
    for url in (
        web,
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ):
        out = checks.check_http({"url": url}, 2)
        assert not out.ok and out.error_kind == "blocked", url


def test_ssrf_blocks_redirect_to_internal_host(web: str, monkeypatch: pytest.MonkeyPatch) -> None:
    real = checks.resolve

    def fake(host: str, port: int, *, allow_private: bool) -> tuple[str, float]:
        if host == "internal.test":
            if not allow_private:
                raise PermissionError("ichki")
            return "127.0.0.1", 0.0
        return real(host, port, allow_private=True)

    monkeypatch.setattr(checks, "resolve", fake)
    # birinchi hop ruxsat etilgan domen, yo'naltirish ichki manzilga: allow_private=False => to'siladi
    out = checks.check_http(
        {"url": f"{web}/to-private", "resolve_to": "127.0.0.1", "allow_private": False}, 3
    )
    assert not out.ok and out.error_kind == "blocked"


def test_ssrf_resolve_to_internal_rejected_unless_allowed(web: str) -> None:
    blocked = checks.check_http({"url": "http://example.com/", "resolve_to": "10.1.2.3"}, 2)
    assert not blocked.ok and blocked.error_kind == "blocked"


def test_is_blocked_ranges() -> None:
    for ip in (
        "10.1.1.1",
        "172.16.0.1",
        "192.168.0.1",
        "127.0.0.1",
        "169.254.1.1",
        "::1",
        "fe80::1",
        "0.0.0.0",  # noqa: S104
        "224.0.0.1",
    ):
        assert checks.is_blocked(ip), ip
    for ip in ("164.68.105.194", "8.8.8.8", "2606:4700::1111"):
        assert not checks.is_blocked(ip), ip


# ---------------------------------------------------------------- TCP
def test_tcp_open_closed_and_expectation(web: str) -> None:
    port = int(web.rsplit(":", 1)[1])
    cfg = {"host": "127.0.0.1", "port": port, "allow_private": True}
    assert checks.check_tcp(cfg, 2).ok
    assert not checks.check_tcp(
        {**cfg, "expect": "closed"}, 2
    ).ok  # ochiq, lekin yopiq kutilgan (AL-030 mantiqi)
    closed = {**cfg, "port": closed_port()}
    assert not checks.check_tcp(closed, 6).ok  # Windows yopiq portda ~2 s kutadi
    assert checks.check_tcp({**closed, "expect": "closed"}, 6).ok
    assert checks.check_tcp({"host": "127.0.0.1", "port": port}, 2).error_kind == "blocked"


# ---------------------------------------------------------------- konfiguratsiya tekshiruvi
@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("http", {"url": "ftp://x.uz/"}),
        ("http", {"url": "https://u:p@x.uz/"}),
        ("http", {"url": "https://x.uz/", "method": "POST"}),
        ("http", {"url": "https://x.uz/", "expected_status": []}),
        ("http", {"url": "https://x.uz/", "expected_status": ["abc"]}),
        ("http", {"url": "https://x.uz/", "expected_status": [99]}),
        ("http", {"url": "https://x.uz/", "keyword": {"text": ""}}),
        ("http", {"url": "https://x.uz/", "headers": {"Host": "evil"}}),
        ("http", {"url": "https://x.uz/", "headers": {"X": 1}}),
        ("http", {"url": "https://x.uz/", "max_redirects": 99}),
        ("http", {"url": "https://x.uz/", "verify_tls": "yes"}),
        ("http", {"url": "https://x.uz/", "resolve_to": "not-ip"}),
        ("http", {"url": "https://x.uz/", "bilinmaydi": 1}),
        ("tcp", {"host": "", "port": 80}),
        ("tcp", {"host": "x.uz", "port": 70000}),
        ("tcp", {"host": "x.uz", "port": True}),
        ("tcp", {"host": "x.uz", "port": 80, "expect": "maybe"}),
        ("dns", {"name": "x.uz"}),
    ],
)
def test_invalid_probe_configs_rejected(kind: str, config: dict[str, Any]) -> None:
    with pytest.raises(services.ProbeConfigError):
        services.validate_config(kind, config)


def test_valid_probe_configs_accepted() -> None:
    services.validate_config(
        "http",
        {
            "url": "https://nazar.avlo.ai/healthz/",
            "expected_status": ["200-299", 301],
            "keyword": {"text": "ok"},
            "headers": {"X-Check": "n"},
            "resolve_to": "164.68.105.194",
            "primary": True,
        },
    )
    services.validate_config("tcp", {"host": "164.68.105.194", "port": 5432, "expect": "closed"})


# ---------------------------------------------------------------- holat mashinasi
def make_probe(**kw: Any) -> Probe:
    defaults: dict[str, Any] = {
        "type": "http",
        "name": "t",
        "config": {"url": "https://x.uz/"},
        "interval_s": 60,
    }
    return Probe.objects.create(**{**defaults, **kw})


def ok_outcome() -> checks.Outcome:
    return checks.Outcome(True, 200, 120)


def bad_outcome() -> checks.Outcome:
    return checks.Outcome(False, 503, 90, error_kind="status")


def test_three_consecutive_failures_needed_for_down_with_fast_retries() -> None:
    probe = make_probe()
    now = timezone.now()
    services.apply_outcome(probe, ok_outcome(), now)
    assert probe.state == "up" and probe.consecutive_failures == 0
    for n in (1, 2):
        services.apply_outcome(probe, bad_outcome(), now)
        assert probe.state == "up" and probe.consecutive_failures == n  # tasdiqlanmagan
        assert probe.next_run_at - now == timedelta(
            seconds=services.RETRY_S
        )  # 15 s da qayta tekshiriladi
    services.apply_outcome(probe, bad_outcome(), now)
    assert probe.state == "down" and probe.state_since == now
    assert (
        timedelta(seconds=53) < probe.next_run_at - now < timedelta(seconds=67)
    )  # oddiy interval (±10%)
    services.apply_outcome(probe, ok_outcome(), now + timedelta(minutes=5))
    assert probe.state == "up" and probe.consecutive_failures == 0  # bitta muvaffaqiyat = up


def test_unknown_stays_unknown_until_three_failures() -> None:
    probe = make_probe()
    now = timezone.now()
    services.apply_outcome(probe, bad_outcome(), now)
    services.apply_outcome(probe, bad_outcome(), now)
    assert probe.state == "unknown"
    services.apply_outcome(probe, bad_outcome(), now)
    assert probe.state == "down"


def test_results_stored_with_uptime_and_history() -> None:
    probe = make_probe()
    now = timezone.now()
    for i, out in enumerate([ok_outcome(), ok_outcome(), bad_outcome(), ok_outcome()]):
        services.store_result(probe, now - timedelta(minutes=10 - i), out)
    rows = services.recent_results(probe.pk, None, None, 10)
    assert [r["ok"] for r in rows] == [True, False, True, True]  # yangisi birinchi
    window = services.recent_results(probe.pk, now - timedelta(minutes=8, seconds=30), None, 10)
    assert len(window) == 2  # faqat -8 va -7 daqiqadagilar
    up = services.uptime(probe.pk, now=now)
    assert up["1d"] == {"checks": 4, "uptime_percent": 75.0} and up["90d"]["checks"] == 4
    assert services.uptime(make_probe(name="bo'sh").pk)["7d"] == {
        "checks": 0,
        "uptime_percent": None,
    }


def test_run_due_claims_executes_in_parallel_and_skips_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = timezone.now()
    due = [make_probe(name=f"d{i}", next_run_at=now - timedelta(seconds=1)) for i in range(3)]
    later = make_probe(name="kech", next_run_at=now + timedelta(hours=1))
    disabled = make_probe(name="o'chiq", enabled=False, next_run_at=now - timedelta(seconds=1))
    seen: list[str] = []

    def fake(kind: str, config: dict[str, Any], timeout: int) -> checks.Outcome:
        seen.append(kind)
        return ok_outcome()

    monkeypatch.setattr(checks, "run_check", fake)
    assert services.run_due(now) == 3
    for p in due:
        p.refresh_from_db()
        assert p.state == "up" and p.last_run_at is not None and p.next_run_at > now
    for p in (later, disabled):
        p.refresh_from_db()
        assert p.last_run_at is None
    assert services.run_due(now) == 0  # qayta olinmaydi: next_run_at surilgan


def test_unexpected_checker_crash_is_a_failure_not_a_dead_prober(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = make_probe(next_run_at=timezone.now() - timedelta(seconds=1))

    def boom(*a: Any, **k: Any) -> checks.Outcome:
        raise RuntimeError("kutilmagan")

    monkeypatch.setattr(checks, "run_check", boom)
    assert services.run_due() == 1
    probe.refresh_from_db()
    assert probe.consecutive_failures == 1


def test_ensure_domain_probes_idempotent() -> None:
    p = Project.objects.create(slug="n-1", name="N", kind="static")
    d = Domain.objects.create(fqdn="n.example.uz", project=p)
    assert len(services.ensure_domain_probes(d)) == 1
    assert services.ensure_domain_probes(d) == []
    probe = Probe.objects.get()
    assert probe.config["url"] == "https://n.example.uz/" and probe.project == p


def test_run_prober_command_once(monkeypatch: pytest.MonkeyPatch) -> None:
    make_probe(next_run_at=timezone.now() - timedelta(seconds=1))
    monkeypatch.setattr(checks, "run_check", lambda *a, **k: ok_outcome())
    call_command("run_prober", once=True)
    assert Probe.objects.get().state == "up"


# ---------------------------------------------------------------- API
def client_for(name: str, role: str) -> Client:
    make_user(name, role)
    c = csrf_client()
    login(c, name)
    return c


def api(c: Client, method: str, url: str, body: Any = None) -> Any:
    return getattr(c, method)(
        url,
        data=json.dumps(body) if body is not None else None,
        content_type="application/json",
        headers=csrf_headers(c),
    )


def test_probe_api_lifecycle_and_permissions(web: str) -> None:
    owner, operator, viewer = (
        client_for("egasi", "owner"),
        client_for("operator", "operator"),
        client_for("kuzatuvchi", "viewer"),
    )
    body = {
        "type": "http",
        "name": "Nazar healthz",
        "config": {"url": "https://nazar.avlo.ai/healthz/", "expected_status": [200]},
        "interval_s": 60,
    }
    created = api(operator, "post", "/api/v1/probes/", body)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert api(viewer, "post", "/api/v1/probes/", body).status_code == 403
    assert [p["id"] for p in viewer.get("/api/v1/probes/").json()["items"]] == [pid]
    assert viewer.get("/api/v1/probes/?type=tcp").json()["items"] == []
    assert viewer.get(f"/api/v1/probes/{pid}").json()["last_result"] is None

    patched = api(operator, "patch", f"/api/v1/probes/{pid}", {"interval_s": 120, "enabled": False})
    assert (
        patched.status_code == 200
        and patched.json()["interval_s"] == 120
        and patched.json()["enabled"] is False
    )
    assert api(operator, "patch", f"/api/v1/probes/{pid}", {"type": "tcp"}).status_code == 400
    assert api(operator, "patch", f"/api/v1/probes/{pid}", {"interval_s": 5}).status_code == 400
    assert api(operator, "patch", f"/api/v1/probes/{pid}", {"timeout_s": 500}).status_code == 400
    assert (
        api(operator, "patch", f"/api/v1/probes/{pid}", {"config": {"url": "bad"}}).status_code
        == 400
    )
    assert api(viewer, "patch", f"/api/v1/probes/{pid}", {"enabled": True}).status_code == 403

    # zudlik bilan bir marta bajarish (mahalliy server: allow_private faqat owner)
    local = {
        "type": "http",
        "name": "mahalliy",
        "config": {"url": f"{web}/ok", "allow_private": True},
    }
    assert api(operator, "post", "/api/v1/probes/", local).status_code == 403  # SSRF: faqat Owner
    lid = api(owner, "post", "/api/v1/probes/", local).json()["id"]
    run = api(operator, "post", f"/api/v1/probes/{lid}/run")
    assert run.status_code == 200 and run.json()["ok"] is True and run.json()["status_code"] == 200
    assert viewer.get(f"/api/v1/probes/{lid}").json()["last_result"]["ok"] is True
    results = viewer.get(f"/api/v1/probes/{lid}/results?limit=5").json()["items"]
    assert len(results) == 1 and results[0]["status_code"] == 200
    assert viewer.get(f"/api/v1/probes/{lid}/results?limit=9999").status_code == 400
    assert viewer.get(f"/api/v1/probes/{lid}/results?from=yomon").status_code == 400
    assert viewer.get(f"/api/v1/probes/{lid}/uptime").json()["1d"]["uptime_percent"] == 100.0

    assert api(operator, "delete", f"/api/v1/probes/{pid}").status_code == 403
    assert api(owner, "delete", f"/api/v1/probes/{pid}").status_code == 204
    probe = Probe.objects.get(pk=pid)
    assert probe.enabled is False and probe.state == "paused"
    enabled = api(operator, "patch", f"/api/v1/probes/{pid}", {"enabled": True})
    assert enabled.json()["state"] == "unknown"  # qayta yoqilganda yangidan boshlanadi
    assert (
        api(owner, "get", "/api/v1/probes/00000000-0000-7000-8000-000000000000").status_code == 404
    )


# ---------------------------------------------------------------- alertlar
def project_with_probe(
    *, primary: bool, state: str = "down", moved: bool = True, server: Server | None = None
) -> Probe:
    project = Project.objects.create(slug="nazar", name="Nazar", kind="compose", moved=moved)
    if server is not None:
        ProjectServer.objects.create(project=project, server=server)
    domain = Domain.objects.create(fqdn="nazar.avlo.ai", project=project)
    return Probe.objects.create(
        project=project, domain=domain, type="http", name="nazar.avlo.ai HTTP", state=state,
        state_since=timezone.now() - timedelta(minutes=3), config={"url": "https://nazar.avlo.ai/", "primary": primary},
    )  # fmt: skip


@pytest.fixture(autouse=True)
def _rules(db: None) -> None:
    sync_built_in()
    AlertInstance.objects.all().delete()


def only_probe_rules() -> None:
    from apps.alerts.models import AlertRule

    AlertRule.objects.exclude(key__in=["AL-049", "AL-049H", "AL-085"]).update(enabled=False)


def test_primary_site_down_is_critical_other_is_high() -> None:
    only_probe_rules()
    channel()
    probe = project_with_probe(primary=True)
    services.store_result(probe, timezone.now(), bad_outcome())
    run_cycle()
    incident = Incident.objects.get()
    assert incident.severity == "critical" and incident.scope_key == f"project:{probe.project_id}"
    (n,) = Notification.objects.all()
    assert (
        "Sayt ishlamayapti: nazar.avlo.ai HTTP" in n.payload["text"]
        and "Loyiha: Nazar" in n.payload["text"]
    )
    assert "HTTP 503, status" in n.payload["text"]  # oxirgi xato sababi
    assert any("callback_data" in b for b in n.payload["buttons"])  # ack tugmalari

    Incident.objects.all().delete()
    AlertInstance.objects.all().delete()
    Notification.objects.all().delete()
    Probe.objects.all().update(config={"url": "https://nazar.avlo.ai/", "primary": False})
    run_cycle()
    assert Incident.objects.get().severity == "high"


def test_recovered_site_closes_incident() -> None:
    only_probe_rules()
    channel()
    probe = project_with_probe(primary=True)
    run_cycle(timezone.now())
    Probe.objects.filter(pk=probe.pk).update(state="up")
    run_cycle(timezone.now() + timedelta(seconds=1))
    run_cycle(timezone.now() + timedelta(seconds=70))
    assert Incident.objects.get().status == "resolved"
    assert any("Tiklandi" in n.payload["text"] for n in Notification.objects.all())


def test_unknown_unmoved_archived_and_disabled_probes_never_alert() -> None:
    only_probe_rules()
    channel()
    project_with_probe(primary=True, state="unknown")
    run_cycle()
    assert not Incident.objects.exists()
    Probe.objects.update(state="down")
    Project.objects.update(moved=False)
    run_cycle()
    assert not Incident.objects.exists()  # FR-REG-007
    Project.objects.update(moved=True, status="archived")
    run_cycle()
    assert not Incident.objects.exists()
    Project.objects.update(status="active")
    Probe.objects.update(enabled=False)
    run_cycle()
    assert not Incident.objects.exists()


def test_site_alert_suppressed_while_its_only_server_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    only_probe_rules()
    from apps.alerts.models import AlertRule

    AlertRule.objects.filter(key="AL-001").update(enabled=True)
    channel()
    s = Server.objects.create(
        name="main-2",
        public_ipv4="164.68.105.194",
        status="online",
        last_seen_at=timezone.now() - timedelta(hours=1),
    )
    project_with_probe(primary=True, server=s)
    # server o'chgan: AL-001 firing (TCP tekshiruvini soxtalashtiramiz)
    from apps.alerts import conditions

    monkeypatch.setattr(conditions, "tcp_probe", lambda *a, **k: False)
    run_cycle()
    by_rule = {
        i.rule.key: i for i in AlertInstance.objects.select_related("rule").filter(state="firing")
    }
    assert "AL-049" in by_rule and by_rule["AL-049"].suppressed is True
    assert [n.payload["text"].split("</b>")[0] for n in Notification.objects.all()] == [
        "🔴 <b>Server o'chdi: main-2"
    ]


def test_silence_by_project_and_maintenance_suppress_site_alert() -> None:
    from apps.alerts.models import MaintenanceWindow, Silence

    only_probe_rules()
    channel()
    s = Server.objects.create(name="main-2", status="online", last_seen_at=timezone.now())
    probe = project_with_probe(primary=True, server=s)
    Silence.objects.create(
        matchers=[{"label": "project", "op": "=", "value": "Nazar"}],
        starts_at=timezone.now() - timedelta(hours=1),
        ends_at=timezone.now() + timedelta(hours=1),
        reason="t",
    )
    run_cycle()
    assert Incident.objects.get().suppressed and not Notification.objects.exists()
    Silence.objects.all().delete()
    MaintenanceWindow.objects.create(
        scope={"projects": [str(probe.project_id)]},
        starts_at=timezone.now() - timedelta(hours=1),
        ends_at=timezone.now() + timedelta(hours=1),
        reason="t",
    )
    AlertInstance.objects.update(notified_at=None)
    run_cycle()
    assert not Notification.objects.exists()


def test_prober_stalled_alert() -> None:
    only_probe_rules()
    channel()
    probe = make_probe(created_at=timezone.now() - timedelta(minutes=10))
    run_cycle()
    assert (
        AlertInstance.objects.get(rule__key="AL-085").state == "firing"
    )  # hech qachon bajarilmagan
    Probe.objects.filter(pk=probe.pk).update(last_run_at=timezone.now())
    run_cycle(timezone.now() + timedelta(seconds=1))
    run_cycle(timezone.now() + timedelta(seconds=70))
    assert AlertInstance.objects.get(rule__key="AL-085").state == "ok"
