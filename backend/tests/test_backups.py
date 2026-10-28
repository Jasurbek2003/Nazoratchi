"""Zaxira monitoringi (B10): tarix, holat, AL-068..072/075, API (FR-BKP-001..005, 010)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.alerts.catalog import sync_built_in
from apps.alerts.conditions import ConditionError, validate_condition
from apps.alerts.engine import run_cycle
from apps.alerts.models import AlertInstance, Incident
from apps.backups import services
from apps.backups.models import BackupRun
from apps.notifications.models import Notification
from apps.registry.models import Project, ProjectServer, Server

from .test_accounts import csrf_client, csrf_headers, login, make_user
from .test_alerts import T0, channel, new_server, only, put

pytestmark = pytest.mark.django_db

GB = 1_000_000_000


@pytest.fixture(autouse=True)
def _rules(db: None) -> None:
    sync_built_in()


def project(
    slug: str = "BiznesRadar", server: Server | None = None, *, daily: bool = True, **extra: Any
) -> Project:
    p = Project.objects.create(
        slug=slug, name=slug, kind="compose", backup={"expect_daily": daily, "db": "postgres17"},
        created_at=extra.pop("created_at", T0 - timedelta(days=30)), **extra,
    )  # fmt: skip
    if server is not None:
        ProjectServer.objects.create(project=p, server=server, environment="production")
    return p


def report(
    server: Server,
    slug: str,
    *,
    at: datetime,
    success_ago_h: float = 2,
    size: float = 50e6,
    status: float = 1,
    **kinds: float,
) -> None:
    """Agent `backup_*` metrikalarini yuboradi."""
    put(server, "backup_last_status", status, at, project=slug)
    put(
        server,
        "backup_last_success_timestamp",
        (at - timedelta(hours=success_ago_h)).timestamp(),
        at,
        project=slug,
    )
    put(server, "backup_last_size_bytes", size, at, project=slug)
    put(
        server,
        "backup_newest_file_age_seconds",
        success_ago_h * 3600,
        at,
        project=slug,
        kind="daily",
    )
    put(server, "backup_files_count", kinds.get("daily", 7), at, project=slug, kind="daily")
    put(server, "backup_files_count", kinds.get("weekly", 4), at, project=slug, kind="weekly")


# ---------------------------------------------------------------- tarix
def test_sync_runs_records_each_new_success_once() -> None:
    s = new_server()
    report(s, "BiznesRadar", at=T0, success_ago_h=3, size=48e6)
    assert services.sync_runs(T0) == 1
    assert services.sync_runs(T0) == 0  # idempotent
    run = BackupRun.objects.get()
    assert (run.project_slug, run.kind, run.size_bytes) == ("BiznesRadar", "daily", 48_000_000)
    report(s, "BiznesRadar", at=T0 + timedelta(days=1), success_ago_h=1, size=51e6)
    assert services.sync_runs(T0 + timedelta(days=1)) == 1
    assert BackupRun.objects.count() == 2


def test_cycle_syncs_runs_automatically() -> None:
    s = new_server()
    report(s, "BiznesRadar", at=timezone.now(), success_ago_h=1)
    run_cycle(timezone.now())
    assert BackupRun.objects.count() == 1


def history(server: Server, slug: str, sizes: list[float], offset: int = 0) -> None:
    for i, size in enumerate(sizes):
        BackupRun.objects.create(
            server=server, project_slug=slug, size_bytes=int(size),
            finished_at=T0 - timedelta(days=len(sizes) + offset - i),
        )  # fmt: skip


def test_size_check_needs_eight_runs_and_uses_median_of_previous_seven() -> None:
    s = new_server()
    history(s, "p", [50e6] * 7)
    assert services.size_check(s.pk, "p") is None  # birinchi 7 zaxirada faqat ma'lumot
    history_extra = BackupRun.objects.create(
        server=s, project_slug="p", finished_at=T0, size_bytes=int(20e6)
    )
    check = services.size_check(s.pk, "p")
    assert (
        check is not None
        and check.median == 50e6
        and check.ratio == pytest.approx(0.4)
        and check.latest == history_extra.size_bytes
    )
    BackupRun.objects.filter(pk=history_extra.pk).update(size_bytes=0)
    BackupRun.objects.filter(project_slug="p").exclude(pk=history_extra.pk).update(size_bytes=0)
    assert services.size_check(s.pk, "p") is None  # median 0: nisbat ma'nosiz


def test_status_of_all_states() -> None:
    now = T0
    fresh = services.ProjectBackup(
        "s",
        "p",
        last_status=1,
        last_success_ts=(now - timedelta(hours=5)).timestamp(),
        seen_at=now - timedelta(minutes=2),
    )
    assert services.status_of(fresh, True, 1000, now)[0] == "ok"
    late = services.ProjectBackup(
        "s",
        "p",
        last_status=1,
        last_success_ts=(now - timedelta(hours=30)).timestamp(),
        seen_at=now,
    )
    assert services.status_of(late, True, 1000, now)[0] == "late"
    critical = services.ProjectBackup(
        "s",
        "p",
        last_status=1,
        last_success_ts=(now - timedelta(hours=60)).timestamp(),
        seen_at=now,
    )
    assert services.status_of(critical, True, 1000, now)[0] == "critical"
    failed = services.ProjectBackup(
        "s", "p", last_status=0, last_success_ts=(now - timedelta(hours=5)).timestamp(), seen_at=now
    )
    assert services.status_of(failed, True, 1000, now)[0] == "failed"
    silent = services.ProjectBackup(
        "s",
        "p",
        last_status=1,
        last_success_ts=(now - timedelta(hours=5)).timestamp(),
        seen_at=now - timedelta(hours=1),
    )
    assert services.status_of(silent, True, 1000, now)[0] == "stale"
    assert services.status_of(None, True, 100, now)[0] == "missing"
    assert services.status_of(None, True, 5, now)[0] == "unknown"  # yangi loyiha
    assert services.status_of(None, False, 100, now) == ("none", None)


# ---------------------------------------------------------------- qoidalar
def at_cycle(server: Server, slug: str, hours_from_start: float, **kw: Any) -> datetime:
    at = T0 + timedelta(hours=hours_from_start)
    report(server, slug, at=at, **kw)
    return at


def test_late_and_overdue_backup_ladder_notifies_once_with_most_severe() -> None:
    only("AL-068", "AL-069")
    channel()
    s = new_server()
    project(server=s)
    run_cycle(at_cycle(s, "BiznesRadar", 0, success_ago_h=20))
    assert not AlertInstance.objects.filter(state="firing").exists()
    run_cycle(at_cycle(s, "BiznesRadar", 8, success_ago_h=28))  # 26 s dan oshdi
    inst = AlertInstance.objects.get(rule__key="AL-068")
    assert inst.state == "firing" and "28 soat oldin" in inst.detail
    (n,) = Notification.objects.all()
    assert (
        "Zaxira kechikdi: BiznesRadar" in n.payload["text"]
        and "RB-031" in n.payload["text"]
        and "Loyiha: BiznesRadar" in n.payload["text"]
    )
    run_cycle(at_cycle(s, "BiznesRadar", 30, success_ago_h=52))  # 50 s dan oshdi
    assert {i.rule.key for i in AlertInstance.objects.filter(state="firing")} == {
        "AL-068",
        "AL-069",
    }
    assert Incident.objects.get().severity == "critical"
    texts = [x.payload["text"] for x in Notification.objects.order_by("id")]
    assert (
        len(texts) == 2 and "uzoq vaqt olinmadi" in texts[1]
    )  # pastroq zinapoya takror xabar bermaydi


def test_fresh_backup_after_late_resolves() -> None:
    only("AL-068")
    channel()
    s = new_server()
    project(server=s)
    run_cycle(at_cycle(s, "BiznesRadar", 0, success_ago_h=30))
    run_cycle(at_cycle(s, "BiznesRadar", 1, success_ago_h=1))
    run_cycle(at_cycle(s, "BiznesRadar", 1.1, success_ago_h=1.1))
    assert Incident.objects.get().status == "resolved"
    assert any("Tiklandi" in n.payload["text"] for n in Notification.objects.all())


def test_never_backed_up_alerts_only_after_the_project_is_old_enough() -> None:
    only("AL-068")
    s = new_server()
    project(server=s, created_at=T0 - timedelta(hours=5))  # yangi loyiha
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()
    Project.objects.update(created_at=T0 - timedelta(hours=40))
    run_cycle(T0 + timedelta(seconds=1))
    inst = AlertInstance.objects.get()
    assert inst.state == "firing" and "hech qachon olinmagan" in inst.detail


def test_silent_agent_never_creates_backup_alerts() -> None:
    only("AL-068", "AL-070")
    s = new_server()
    project(server=s)
    report(s, "BiznesRadar", at=T0, success_ago_h=40, status=0)
    run_cycle(T0 + timedelta(hours=2))  # agent 2 soat jim: holat noma'lum
    assert not AlertInstance.objects.filter(state="firing").exists()


def test_failed_backup_alert_and_clear() -> None:
    only("AL-070")
    channel()
    s = new_server()
    project(server=s)
    run_cycle(at_cycle(s, "BiznesRadar", 0, success_ago_h=3, status=0))
    (n,) = Notification.objects.all()
    assert (
        "Zaxira muvaffaqiyatsiz: BiznesRadar" in n.payload["text"]
        and "state.json" in n.payload["text"]
    )
    run_cycle(at_cycle(s, "BiznesRadar", 0.5, success_ago_h=0.4, status=1))
    run_cycle(at_cycle(s, "BiznesRadar", 0.6, success_ago_h=0.5, status=1))
    assert Incident.objects.get().status == "resolved"


def test_only_projects_that_expect_daily_backups_are_judged() -> None:
    only("AL-068", "AL-070")
    s = new_server()
    project("statik", server=s, daily=False)
    report(s, "statik", at=T0, success_ago_h=100, status=0)
    p = project("ko'chirilmagan", server=s, moved=False)
    Project.objects.filter(pk=p.pk).update(moved=False)
    report(s, "ko'chirilmagan", at=T0, success_ago_h=100, status=0)
    project("serversiz", daily=True)  # qaysi serverda ekani noma'lum
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()


def test_size_anomaly_small_and_large() -> None:
    only("AL-071", "AL-072")
    channel("info")
    s = new_server()
    project(server=s)
    history(s, "BiznesRadar", [50e6] * 7)
    BackupRun.objects.create(
        server=s,
        project_slug="BiznesRadar",
        finished_at=T0 - timedelta(hours=1),
        size_bytes=int(10e6),
    )
    report(s, "BiznesRadar", at=T0, success_ago_h=1, size=10e6)
    run_cycle(T0)
    by = {
        i.rule.key: i for i in AlertInstance.objects.select_related("rule").filter(state="firing")
    }
    assert set(by) == {"AL-071"} and "0.20x" in by["AL-071"].detail
    (n,) = Notification.objects.all()
    assert "shubhali: juda kichik" in n.payload["text"] and "RB-032" in n.payload["text"]

    BackupRun.objects.filter(
        project_slug="BiznesRadar", finished_at=T0 - timedelta(hours=1)
    ).update(size_bytes=int(200e6))
    run_cycle(T0 + timedelta(seconds=1))
    run_cycle(T0 + timedelta(seconds=70))
    assert AlertInstance.objects.get(rule__key="AL-071").state == "ok"
    assert AlertInstance.objects.get(rule__key="AL-072").state == "firing"  # 4x > 3x


def test_size_anomaly_silent_during_first_week_and_when_normal() -> None:
    only("AL-071", "AL-072")
    s = new_server()
    project(server=s)
    history(s, "BiznesRadar", [50e6] * 3)
    BackupRun.objects.create(
        server=s,
        project_slug="BiznesRadar",
        finished_at=T0 - timedelta(hours=1),
        size_bytes=int(1e6),
    )
    report(s, "BiznesRadar", at=T0, success_ago_h=1)
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()  # tarix < 8
    history(s, "BiznesRadar", [50e6] * 6, offset=5)
    BackupRun.objects.filter(finished_at=T0 - timedelta(hours=1)).update(size_bytes=int(55e6))
    run_cycle(T0 + timedelta(seconds=1))
    assert not AlertInstance.objects.filter(state="firing").exists()


def test_offsite_not_configured_warning_is_persistent() -> None:
    only("AL-075")
    channel()
    s = new_server()
    put(s, "backup_offsite_configured", 0, T0)
    run_cycle(T0)
    inst = AlertInstance.objects.get()
    assert inst.state == "firing" and inst.rule.severity == "warning"
    put(s, "backup_offsite_configured", 1, T0 + timedelta(minutes=5))
    run_cycle(T0 + timedelta(minutes=5))
    run_cycle(T0 + timedelta(minutes=7))
    assert Incident.objects.get().status == "resolved"


def test_backup_alert_silenced_with_project_matcher() -> None:
    from apps.alerts.models import Silence

    only("AL-068")
    channel()
    s = new_server()
    project(server=s)
    Silence.objects.create(
        matchers=[{"label": "project", "op": "=", "value": "BiznesRadar"}],
        starts_at=T0 - timedelta(days=1),
        ends_at=T0 + timedelta(days=2),
        reason="t",
    )
    run_cycle(at_cycle(s, "BiznesRadar", 0, success_ago_h=30))
    assert Incident.objects.get().suppressed and not Notification.objects.exists()


def test_backup_condition_validation() -> None:
    validate_condition({"type": "state", "source": "backup", "field": "age_hours_gt", "equals": 26})
    validate_condition({"type": "state", "source": "backup", "field": "size_small", "equals": True})
    for bad in (
        {"type": "state", "source": "backup", "field": "age_hours_gt", "equals": True},
        {"type": "state", "source": "backup", "field": "size_small", "equals": 5},
        {"type": "state", "source": "backup", "field": "yoq", "equals": True},
    ):
        with pytest.raises(ConditionError):
            validate_condition(bad)


# ---------------------------------------------------------------- API
def client_for(name: str, role: str) -> Client:
    make_user(name, role)
    c = csrf_client()
    login(c, name)
    return c


def test_backups_list_and_card() -> None:
    viewer = client_for("kuzatuvchi", "viewer")
    now = timezone.now()
    s = new_server()
    project(server=s, created_at=now - timedelta(days=30))
    project("statik", server=s, daily=False)  # siyosat bor, lekin hech narsa kutilmaydi
    Project.objects.create(
        slug="siyosatsiz", name="x", kind="static"
    )  # siyosat ham, ma'lumot ham yo'q: ro'yxatda yo'q
    report(s, "BiznesRadar", at=now, success_ago_h=3, size=48e6, daily=7, weekly=4)
    put(s, "backup_offsite_configured", 0, now)
    for i in range(9):
        BackupRun.objects.create(
            server=s,
            project_slug="BiznesRadar",
            finished_at=now - timedelta(days=9 - i),
            size_bytes=50_000_000 if i < 8 else 10_000_000,
        )
    body = viewer.get("/api/v1/backups/").json()["items"]
    assert [i["project"] for i in body] == ["BiznesRadar", "statik"]
    br = body[0]
    assert (
        br["state"] == "ok"
        and br["last_status"] == "ok"
        and br["server"] == "main-2"
        and br["daily_count"] == 7
        and br["weekly_count"] == 4
    )
    assert (
        br["age_hours"] == 3.0
        and br["last_size_bytes"] == 48_000_000
        and br["offsite_configured"] is False
    )
    assert body[1]["state"] == "none"
    card = viewer.get("/api/v1/backups/BiznesRadar").json()
    assert (
        len(card["runs"]) == 9 and card["runs"][0]["finished_at"] < card["runs"][-1]["finished_at"]
    )  # eskidan yangiga
    assert (
        card["size_median_7"] == 50_000_000
        and card["size_anomaly"] is True
        and card["size_ratio"] == 0.2
    )
    assert viewer.get("/api/v1/backups/yoq").status_code == 404
    assert Client().get("/api/v1/backups/").status_code in (401, 403)


def test_backup_policy_in_project_api_is_validated() -> None:
    op = client_for("operator", "operator")

    def create(backup: Any, slug: str) -> Any:
        return op.post(
            "/api/v1/projects/", data=json.dumps({"slug": slug, "name": "x", "kind": "compose", "backup": backup}),
            content_type="application/json", headers=csrf_headers(op),
        )  # fmt: skip

    ok = create({"expect_daily": True, "require_offsite": True, "db": "postgres16"}, "a-1")
    assert ok.status_code == 201 and ok.json()["backup"]["expect_daily"] is True
    for bad in ({"expect_daily": "ha"}, {"nomalum": 1}, {"db": "x" * 40}, "matn"):
        assert create(bad, f"b-{abs(hash(str(bad))) % 1000}").status_code == 400


def test_seed_loads_backup_policy() -> None:
    from django.core.management import call_command

    call_command("seed_registry")
    nazar = Project.objects.get(slug="Nazar")
    assert nazar.backup == {"expect_daily": True, "require_offsite": True, "db": "postgres16"}
    assert Project.objects.get(slug="BiznesRadar").backup["expect_weekly_files"] is True
    assert Project.objects.get(slug="avlo_site").backup == {"expect_daily": False}
    assert Project.objects.get(slug="Matnchi").backup == {}
    assert UTC is not None


# ---------------------------------------------------------------- restore drill alertlari (AL-081..083)
def drill(p: Project, *, days_ago: float, result: str = "success", notes: str = "") -> None:
    from apps.backups.models import RestoreDrill

    RestoreDrill.objects.create(
        project=p,
        performed_at=T0 - timedelta(days=days_ago),
        backup_file="x.sql.gz",
        result=result,
        notes=notes,
    )


def firing_keys() -> set[str]:
    return {a.rule.key for a in AlertInstance.objects.filter(state="firing").select_related("rule")}


def test_never_drilled_is_overdue_but_not_due_soon() -> None:
    only("AL-081", "AL-082", "AL-083")
    channel()
    s = new_server()
    project("BiznesRadar", s)
    run_cycle(T0)
    assert firing_keys() == {"AL-082"}
    inst = AlertInstance.objects.get(rule__key="AL-082")
    assert inst.rule.severity == "warning" and "hech qachon" in inst.detail


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [(10, set()), (80, {"AL-081"}), (90, {"AL-081"}), (91, {"AL-082"}), (200, {"AL-082"})],
)
def test_drill_age_thresholds(days_ago: int, expected: set[str]) -> None:
    only("AL-081", "AL-082", "AL-083")
    channel()
    s = new_server()
    drill(project("BiznesRadar", s), days_ago=days_ago)
    run_cycle(T0)
    assert firing_keys() == expected


def test_custom_drill_interval_from_policy() -> None:
    only("AL-081", "AL-082")
    channel()
    s = new_server()
    p = project("BiznesRadar", s)
    p.backup = {**p.backup, "drill_every_days": 30}
    p.save()
    drill(p, days_ago=40)
    run_cycle(T0)
    assert firing_keys() == {"AL-082"}


def test_failed_drill_fires_high_and_resolves_after_new_success() -> None:
    only("AL-083")
    channel()
    s = new_server()
    p = project("BiznesRadar", s)
    drill(p, days_ago=2, result="failed", notes="pg_restore: xato")
    run_cycle(T0)
    inst = AlertInstance.objects.get()
    assert inst.state == "firing" and inst.rule.severity == "high" and "pg_restore" in inst.detail
    drill(p, days_ago=0, result="success")
    run_cycle(T0 + timedelta(minutes=1))
    run_cycle(T0 + timedelta(minutes=3))
    assert Incident.objects.get().status == "resolved"


def test_failed_drill_does_not_reset_overdue_timer() -> None:
    only("AL-082", "AL-083")
    channel()
    s = new_server()
    p = project("BiznesRadar", s)
    drill(p, days_ago=120, result="success")
    drill(p, days_ago=1, result="failed")
    run_cycle(T0)
    assert firing_keys() == {"AL-082", "AL-083"}


def test_drill_alerts_skip_projects_without_backup_policy_or_not_moved() -> None:
    only("AL-082")
    channel()
    s = new_server()
    project("A", s, daily=False)
    project("B", s, moved=False)
    run_cycle(T0)
    assert firing_keys() == set()
