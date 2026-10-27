"""Alertlar API: qoidalar, incidentlar, silence, maintenance (TZ 9.8; FR-ALR-001/012/013)."""

import json
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.alerts import services
from apps.alerts.catalog import sync_built_in
from apps.alerts.engine import run_cycle
from apps.alerts.models import AlertInstance, AlertRule, Incident, MaintenanceWindow, Silence
from apps.audit.models import AuditLog

from .test_accounts import csrf_client, csrf_headers, login, make_user
from .test_alerts import T0, alive, channel, new_server, only, put

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _rules(db: None) -> None:
    sync_built_in()


def client_for(login_name: str, role: str) -> Client:
    make_user(login_name, role)
    c = csrf_client()
    login(c, login_name)
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


def open_incident() -> Incident:
    s = new_server()
    channel()
    only("AL-015")
    for minute in (0, 5):
        put(s, "mem_used_percent", 98, T0 + timedelta(minutes=minute))
        alive(s, T0 + timedelta(minutes=minute))
        run_cycle(T0 + timedelta(minutes=minute))
    return Incident.objects.get()


# ---------------------------------------------------------------- qoidalar
def test_rules_list_filters_and_viewer_can_read(viewer: Client) -> None:
    items = viewer.get("/api/v1/alert-rules/").json()["items"]
    assert {r["key"] for r in items} >= {"AL-001", "AL-019"} and all(
        "condition" in r for r in items
    )
    critical = viewer.get("/api/v1/alert-rules/?severity=critical").json()["items"]
    assert critical and all(r["severity"] == "critical" for r in critical)
    assert viewer.get("/api/v1/alert-rules/?built_in=false").json()["items"] == []
    rule_id = items[0]["id"]
    assert viewer.get(f"/api/v1/alert-rules/{rule_id}").json()["id"] == rule_id
    assert viewer.get("/api/v1/alert-rules/00000000-0000-7000-8000-000000000000").status_code == 404
    assert Client().get("/api/v1/alert-rules/").status_code in (401, 403)


def test_patch_rule_threshold_audited_and_validated(operator: Client, viewer: Client) -> None:
    rule = AlertRule.objects.get(key="AL-009")
    new_cond = {**rule.condition, "value": 75}
    ok = call(
        operator,
        "patch",
        f"/api/v1/alert-rules/{rule.pk}",
        {"condition": new_cond, "for_seconds": 300, "severity": "high"},
    )
    assert ok.status_code == 200
    rule.refresh_from_db()
    assert rule.condition["value"] == 75 and rule.for_seconds == 300 and rule.severity == "high"
    entry = AuditLog.objects.get(action="rule.update")
    assert (
        entry.before is not None
        and entry.after is not None
        and entry.before["for_seconds"] == 600
        and entry.after["for_seconds"] == 300
    )
    assert (
        call(
            operator, "patch", f"/api/v1/alert-rules/{rule.pk}", {"condition": {"type": "boom"}}
        ).status_code
        == 400
    )
    assert (
        call(operator, "patch", f"/api/v1/alert-rules/{rule.pk}", {"severity": "zo'r"}).status_code
        == 400
    )
    assert (
        call(
            operator, "patch", f"/api/v1/alert-rules/{rule.pk}", {"scope": {"type": "x"}}
        ).status_code
        == 400
    )
    assert (
        call(
            operator, "patch", f"/api/v1/alert-rules/{rule.pk}", {"key": "HACK", "built_in": False}
        ).status_code
        == 200
    )
    rule.refresh_from_db()
    assert rule.key == "AL-009" and rule.built_in is True  # key va built_in o'zgarmaydi
    assert (
        call(viewer, "patch", f"/api/v1/alert-rules/{rule.pk}", {"enabled": False}).status_code
        == 403
    )


def test_create_custom_rule(operator: Client) -> None:
    body = {
        "name": "Swap yuqori",
        "scope": {"type": "host"},
        "condition": {"type": "threshold", "metric": "swap_used_percent", "op": ">", "value": 50},
        "for_seconds": 600,
        "severity": "warning",
    }
    response = call(operator, "post", "/api/v1/alert-rules/", body)
    assert response.status_code == 201
    data = response.json()
    assert data["key"].startswith("USR-") and data["built_in"] is False and data["enabled"] is True
    assert (
        call(
            operator,
            "post",
            "/api/v1/alert-rules/",
            {**body, "condition": {"type": "and", "of": []}},
        ).status_code
        == 400
    )


def test_rule_dry_run_lists_would_be_firing_without_side_effects(owner: Client) -> None:
    s = new_server()
    channel()
    put(s, "cpu_busy_percent", 99, T0)
    # engine "hozir"da emas, API timezone.now() ishlatadi: ma'lumotni hozirga yaqin yozamiz
    now = timezone.now()
    put(s, "cpu_busy_percent", 99, now)
    rule = AlertRule.objects.get(key="AL-009")
    response = call(owner, "post", f"/api/v1/alert-rules/{rule.pk}/test")
    assert response.status_code == 200
    body = response.json()
    assert body["firing_count"] == 1 and body["items"][0]["subject"] == "main-2"
    assert not AlertInstance.objects.exists() and not Incident.objects.exists()  # holatga tegmaydi


# ---------------------------------------------------------------- incidentlar
def test_incident_list_detail_and_filters(viewer: Client) -> None:
    incident = open_incident()
    listing = viewer.get("/api/v1/incidents/").json()
    assert [i["id"] for i in listing["items"]] == [str(incident.pk)] and listing[
        "next_before"
    ] is None
    assert viewer.get("/api/v1/incidents/?status=resolved").json()["items"] == []
    assert viewer.get("/api/v1/incidents/?filter[status]=open").json()["items"]
    assert viewer.get("/api/v1/incidents/?severity=critical").json()["items"]
    assert viewer.get(f"/api/v1/incidents/?server_id={incident.scope_key.split(':')[1]}").json()[
        "items"
    ]
    assert (
        viewer.get("/api/v1/incidents/?server_id=00000000-0000-7000-8000-000000000000").json()[
            "items"
        ]
        == []
    )
    assert viewer.get("/api/v1/incidents/?from=yomon").status_code == 400
    detail = viewer.get(f"/api/v1/incidents/{incident.pk}").json()
    assert detail["title"].startswith("RAM kritik") and detail["alerts"][0]["rule_key"] == "AL-015"
    assert [e["type"] for e in detail["events"]][:2] == ["opened", "notified"]
    assert viewer.get("/api/v1/incidents/00000000-0000-7000-8000-000000000000").status_code == 404


def test_ack_comment_root_cause_and_resolve_conflict(operator: Client, viewer: Client) -> None:
    incident = open_incident()
    base = f"/api/v1/incidents/{incident.pk}"
    assert call(viewer, "post", f"{base}/ack").status_code == 403
    ack = call(operator, "post", f"{base}/ack", {"comment": "ko'ryapman"})
    assert (
        ack.status_code == 200
        and ack.json()["status"] == "acknowledged"
        and ack.json()["acked_by"] == "operator"
    )
    again = call(operator, "post", f"{base}/ack")
    assert again.status_code == 409 and again.json()["error"]["code"] == "conflict"
    assert AuditLog.objects.filter(action="incident.ack", object_id=str(incident.pk)).exists()

    comment = call(operator, "post", f"{base}/comments", {"text": "RAM sizib chiqyapti"})
    assert comment.status_code == 201 and comment.json()["data"]["text"] == "RAM sizib chiqyapti"
    assert call(operator, "post", f"{base}/comments", {"text": "  "}).status_code == 400

    cause = call(operator, "patch", base, {"root_cause": "xotira oqishi"})
    assert cause.status_code == 200 and cause.json()["root_cause"] == "xotira oqishi"
    assert call(operator, "patch", base, {"root_cause": 5}).status_code == 400

    conflict = call(operator, "post", f"{base}/resolve")
    assert conflict.status_code == 409  # shart hamon rost
    AlertInstance.objects.update(state="ok")
    done = call(operator, "post", f"{base}/resolve")
    assert done.status_code == 200 and done.json()["status"] == "resolved"
    assert call(operator, "post", f"{base}/ack").status_code == 409


def test_services_ack_rejects_resolved() -> None:
    incident = open_incident()
    Incident.objects.filter(pk=incident.pk).update(status="resolved")
    incident.refresh_from_db()
    with pytest.raises(services.IncidentConflict):
        services.ack(incident, None)


def test_active_alerts_endpoint(viewer: Client) -> None:
    open_incident()
    items = viewer.get("/api/v1/alerts/").json()["items"]
    assert len(items) == 1 and items[0]["state"] == "firing" and items[0]["severity"] == "critical"


# ---------------------------------------------------------------- silence
def silence_body(**extra: Any) -> dict[str, Any]:
    return {
        "matchers": [{"label": "server", "op": "=", "value": "main-2"}],
        "ends_at": (timezone.now() + timedelta(hours=2)).isoformat(),
        "reason": "Kernel yangilanishi va reboot",
        **extra,
    }


def test_silence_lifecycle(operator: Client, viewer: Client) -> None:
    created = call(operator, "post", "/api/v1/silences/", silence_body())
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["created_by"] == "operator"
    assert [x["id"] for x in viewer.get("/api/v1/silences/").json()["items"]] == [sid]
    assert AuditLog.objects.filter(action="silence.create", object_id=sid).exists()
    assert call(viewer, "post", "/api/v1/silences/", silence_body()).status_code == 403
    assert call(viewer, "delete", f"/api/v1/silences/{sid}").status_code == 403
    assert call(operator, "delete", f"/api/v1/silences/{sid}").status_code == 204
    assert viewer.get("/api/v1/silences/").json()["items"] == []  # bekor qilinganlar yashirin
    assert len(viewer.get("/api/v1/silences/?all=1").json()["items"]) == 1
    assert call(operator, "delete", f"/api/v1/silences/{sid}").status_code == 404  # ikkinchi marta
    assert Silence.objects.get().cancelled_at is not None


@pytest.mark.parametrize(
    "extra",
    [
        {"reason": "  "},
        {"matchers": []},
        {"matchers": [{"label": "server", "op": "=~", "value": "("}]},
        {"ends_at": "2020-01-01T00:00:00Z"},  # o'tmishda
    ],
)
def test_silence_validation(operator: Client, extra: dict[str, Any]) -> None:
    assert call(operator, "post", "/api/v1/silences/", silence_body(**extra)).status_code == 400
    assert Silence.objects.count() == 0


def test_silence_duration_bounds(operator: Client) -> None:
    soon = {"ends_at": (timezone.now() + timedelta(minutes=5)).isoformat()}
    far = {"ends_at": (timezone.now() + timedelta(days=40)).isoformat()}
    assert (
        call(operator, "post", "/api/v1/silences/", silence_body(**soon)).status_code == 400
    )  # < 15 daqiqa
    assert (
        call(operator, "post", "/api/v1/silences/", silence_body(**far)).status_code == 400
    )  # > 30 kun
    edge = {"ends_at": (timezone.now() + timedelta(days=30)).isoformat()}
    assert call(operator, "post", "/api/v1/silences/", silence_body(**edge)).status_code == 201


def test_silence_created_via_api_suppresses_engine(operator: Client) -> None:
    s = new_server()
    channel()
    only("AL-015")
    call(
        operator,
        "post",
        "/api/v1/silences/",
        silence_body(ends_at=(timezone.now() + timedelta(days=1)).isoformat()),
    )
    now = timezone.now()
    for minute in (0, 5):
        at = now + timedelta(minutes=minute)
        put(s, "mem_used_percent", 99, at)
        alive(s, at)
        run_cycle(at)
    incident = Incident.objects.get()
    assert incident.suppressed is True
    from apps.notifications.models import Notification

    assert Notification.objects.count() == 0


# ---------------------------------------------------------------- maintenance
def test_maintenance_lifecycle_and_validation(operator: Client, viewer: Client) -> None:
    s = new_server()
    start = timezone.now()
    body = {
        "scope": {"servers": [str(s.pk)]},
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=1)).isoformat(),
        "reason": "Reboot",
    }
    created = call(operator, "post", "/api/v1/maintenance/", body)
    assert created.status_code == 201
    mid = created.json()["id"]
    assert [x["id"] for x in viewer.get("/api/v1/maintenance/").json()["items"]] == [mid]
    for bad in (
        {**body, "scope": {}},
        {**body, "scope": {"servers": []}},
        {**body, "scope": {"servers": [1]}},
        {**body, "scope": {"hosts": ["a"]}},
        {**body, "ends_at": start.isoformat()},
        {**body, "reason": " "},
        {**body, "ends_at": (start + timedelta(days=45)).isoformat()},
    ):
        assert call(operator, "post", "/api/v1/maintenance/", bad).status_code == 400, bad
    assert call(viewer, "post", "/api/v1/maintenance/", body).status_code == 403
    assert call(operator, "delete", f"/api/v1/maintenance/{mid}").status_code == 204
    assert MaintenanceWindow.objects.get().cancelled_at is not None
    assert AuditLog.objects.filter(action="maintenance.cancel").exists()
