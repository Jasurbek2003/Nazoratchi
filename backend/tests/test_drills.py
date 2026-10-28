"""Restore drill (UC-11, FR-BKP-016, T-BKP-09): kiritish, tuzatish, tarix, kartadagi holat."""

import json
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.backups.models import RestoreDrill
from apps.registry.models import Project

from .test_accounts import csrf_client, csrf_headers, login, make_user

pytestmark = pytest.mark.django_db


def client_for(name: str, role: str) -> Client:
    make_user(name, role)
    c = csrf_client()
    login(c, name)
    return c


def call(c: Client, method: str, url: str, body: Any = None) -> Any:
    if method == "get":
        return c.get(url)
    return getattr(c, method)(
        url, data=json.dumps(body or {}), content_type="application/json", headers=csrf_headers(c)
    )


def make_project(slug: str = "BiznesRadar", **backup: Any) -> Project:
    return Project.objects.create(slug=slug, name=slug, backup={"expect_daily": True, **backup})


def payload(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project": "BiznesRadar",
        "performed_at": (timezone.now() - timedelta(hours=1)).isoformat(),
        "backup_file": "BiznesRadar-20261022-031501.sql.gz",
        "backup_age_h": 7,
        "duration_s": 840,
        "tables_count": 42,
        "rows_count": 1_250_000,
        "result": "success",
        "notes": "55432-portli vaqtinchalik postgres:17",
    }
    body.update(over)
    return body


def test_operator_records_drill_and_it_is_audited() -> None:
    make_project()
    op = client_for("operator", "operator")
    r = call(op, "post", "/api/v1/backups/drills", payload())
    assert r.status_code == 201, r.content
    data = r.json()
    assert data["project"] == "BiznesRadar" and data["performed_by"] == "operator"
    assert data["duration_s"] == 840 and data["result"] == "success"
    assert RestoreDrill.objects.count() == 1
    assert AuditLog.objects.filter(action="drill.create", object_id=data["id"]).exists()


def test_viewer_can_read_but_not_write() -> None:
    make_project()
    viewer = client_for("kuzatuvchi", "viewer")
    assert call(viewer, "post", "/api/v1/backups/drills", payload()).status_code == 403
    assert call(viewer, "get", "/api/v1/backups/drills").status_code == 200
    assert RestoreDrill.objects.count() == 0


@pytest.mark.parametrize(
    "over",
    [
        {"project": "yoq-loyiha"},
        {"result": "ajoyib"},
        {"performed_at": (timezone.now() + timedelta(days=2)).isoformat()},
        {"backup_file": "   "},
        {"duration_s": -5},
        {"rows_count": "ko'p"},
        {"notes": "x" * 2001},
    ],
)
def test_invalid_input_is_rejected(over: dict[str, Any]) -> None:
    make_project()
    op = client_for("operator", "operator")
    r = call(op, "post", "/api/v1/backups/drills", payload(**over))
    assert r.status_code == 400, over
    assert RestoreDrill.objects.count() == 0


def test_patch_corrects_fields_and_cannot_move_project() -> None:
    make_project()
    make_project("lutfan_ai")
    op = client_for("operator", "operator")
    drill_id = call(op, "post", "/api/v1/backups/drills", payload()).json()["id"]
    r = call(
        op, "patch", f"/api/v1/backups/drills/{drill_id}", {"duration_s": 900, "result": "partial"}
    )
    assert (
        r.status_code == 200 and r.json()["duration_s"] == 900 and r.json()["result"] == "partial"
    )
    moved = call(op, "patch", f"/api/v1/backups/drills/{drill_id}", {"project": "lutfan_ai"})
    assert moved.status_code == 400
    entry = AuditLog.objects.get(action="drill.update")
    assert entry.before is not None and entry.after is not None
    assert entry.before["duration_s"] == 840 and entry.after["duration_s"] == 900
    assert (
        call(op, "get", "/api/v1/backups/drills/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )


def test_list_filters_and_newest_first() -> None:
    make_project()
    make_project("lutfan_ai")
    op = client_for("operator", "operator")
    older = (timezone.now() - timedelta(days=3)).isoformat()
    call(op, "post", "/api/v1/backups/drills", payload(performed_at=older, result="failed"))
    call(op, "post", "/api/v1/backups/drills", payload())
    call(op, "post", "/api/v1/backups/drills", payload(project="lutfan_ai"))
    allv = call(op, "get", "/api/v1/backups/drills").json()["items"]
    assert len(allv) == 3
    br = call(op, "get", "/api/v1/backups/drills?project=BiznesRadar").json()["items"]
    assert [d["result"] for d in br] == ["success", "failed"]
    failed = call(op, "get", "/api/v1/backups/drills?result=failed").json()["items"]
    assert len(failed) == 1


def test_card_shows_never_then_recent_then_overdue() -> None:
    project = make_project(drill_every_days=30)
    op = client_for("operator", "operator")
    card = call(op, "get", "/api/v1/backups/BiznesRadar").json()
    assert card["drill"]["never"] is True and card["drill"]["overdue"] is True
    assert card["drill"]["last"] is None and card["drills"] == []

    call(op, "post", "/api/v1/backups/drills", payload())
    card = call(op, "get", "/api/v1/backups/BiznesRadar").json()
    assert card["drill"]["never"] is False and card["drill"]["overdue"] is False
    assert card["drill"]["last_success_days"] == 0 and card["drill"]["every_days"] == 30
    assert len(card["drills"]) == 1

    RestoreDrill.objects.update(performed_at=timezone.now() - timedelta(days=45))
    card = call(op, "get", "/api/v1/backups/BiznesRadar").json()
    assert card["drill"]["overdue"] is True and card["drill"]["last_success_days"] == 45
    assert project.slug == "BiznesRadar"


def test_failed_drill_does_not_count_as_success() -> None:
    make_project()
    op = client_for("operator", "operator")
    call(op, "post", "/api/v1/backups/drills", payload(result="failed"))
    drill = call(op, "get", "/api/v1/backups/BiznesRadar").json()["drill"]
    assert drill["last"]["result"] == "failed"
    assert drill["never"] is True and drill["overdue"] is True


def test_list_carries_drill_summary() -> None:
    project = make_project()
    # Ro'yxatda ko'rinishi uchun ko'chirilgan (moved) va faol bo'lishi kerak.
    Project.objects.filter(pk=project.pk).update(moved=True)
    op = client_for("operator", "operator")
    call(op, "post", "/api/v1/backups/drills", payload())
    items = call(op, "get", "/api/v1/backups/").json()["items"]
    assert items and items[0]["drill"]["never"] is False
