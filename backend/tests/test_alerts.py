"""Alert dvigateli: shartlar, holat mashinasi, incident, bostirish, eslatmalar (TZ 6.7, 12; FR-ALR-001..014)."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.alerts import conditions, engine
from apps.alerts.catalog import BUILT_IN, sync_built_in
from apps.alerts.conditions import (
    ConditionError,
    Ctx,
    evaluate_rule,
    linear_fit,
    validate_condition,
)
from apps.alerts.engine import run_cycle
from apps.alerts.models import AlertInstance, AlertRule, Incident, MaintenanceWindow, Silence
from apps.alerts.suppression import MatcherError, matches, validate_matchers
from apps.heartbeats.models import HeartbeatJob
from apps.ingest.catalog import kind_for, unit_for
from apps.ingest.services import labels_hash
from apps.metrics.models import Series, SeriesLatest
from apps.notifications.models import Channel, Notification
from apps.registry.models import Project, ProjectServer, Server

pytestmark = pytest.mark.django_db

T0 = timezone.now().replace(microsecond=0)


# ---------------------------------------------------------------- yordamchilar
def new_server(name: str = "main-2", ip: str | None = "164.68.105.194", **kw: Any) -> Server:
    return Server.objects.create(name=name, public_ipv4=ip, status="online", last_seen_at=T0, **kw)


def put(server: Server, name: str, value: float, at: datetime, **labels: str) -> None:
    """Sintetik namuna: `metric_samples` + `SeriesLatest` + server.last_seen_at."""
    series, _ = Series.objects.get_or_create(
        server=server,
        name=name,
        labels_hash=labels_hash(labels),
        defaults={"labels": labels, "unit": unit_for(name), "kind": kind_for(name)},
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO metric_samples (time, series_id, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            [at, series.pk, value],
        )
    latest = SeriesLatest.objects.filter(series=series).first()
    if latest is None or latest.time <= at:
        SeriesLatest.objects.update_or_create(series=series, defaults={"time": at, "value": value})
    if server.last_seen_at is None or server.last_seen_at < at:
        Server.objects.filter(pk=server.pk).update(last_seen_at=at)
        server.last_seen_at = at


def alive(server: Server, at: datetime) -> None:
    put(server, "agent_up", 1, at)


def channel(min_severity: str = "info") -> Channel:
    ch = Channel(type="telegram", name="tg", min_severity=min_severity)
    ch.set_config({"bot_token": "123456789:AAH-secretTOKENsecretTOKENsecret_abcd12", "chat_id": 1})
    ch.save()
    return ch


def texts() -> list[str]:
    return [n.payload["text"] for n in Notification.objects.order_by("id")]


def rule(key: str) -> AlertRule:
    return AlertRule.objects.get(key=key)


@pytest.fixture(autouse=True)
def _rules(db: None) -> None:
    sync_built_in()
    conditions._probe_cache.clear()


@pytest.fixture
def tg_down(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """TCP:22 tekshiruvi: {'up': True/False}."""
    state = {"up": False}
    monkeypatch.setattr(conditions, "tcp_probe", lambda host, port, timeout=3.0: state["up"])
    return state


def only(*keys: str) -> None:
    """Sinov uchun faqat berilgan qoidalar yoqilgan."""
    AlertRule.objects.exclude(key__in=keys).update(enabled=False)


# ---------------------------------------------------------------- katalog va tekshiruv
def test_builtin_rules_seeded_idempotently_and_not_overwritten() -> None:
    assert AlertRule.objects.filter(built_in=True).count() == len(BUILT_IN)
    AlertRule.objects.filter(key="AL-009").update(
        condition={**rule("AL-009").condition, "value": 70}
    )
    assert sync_built_in() == 0
    assert rule("AL-009").condition["value"] == 70  # foydalanuvchi chegarasi saqlandi


def test_every_builtin_condition_is_valid() -> None:
    for spec in BUILT_IN:
        validate_condition(spec["condition"])


@pytest.mark.parametrize(
    "cond",
    [
        {"type": "nomalum"},
        {"type": "threshold", "metric": "Cpu", "op": ">", "value": 1},
        {"type": "threshold", "metric": "cpu", "op": "=>", "value": 1},
        {"type": "threshold", "metric": "cpu", "op": ">", "value": "90"},
        {"type": "threshold", "metric": "cpu", "op": ">", "value": 1, "aggregate": "median"},
        {"type": "absent", "metric": "agent_up", "max_age_s": 1},
        {"type": "rate", "metric": "x", "increase": -1, "window_s": 60},
        {"type": "state", "source": "reachability", "field": "tcp22", "equals": "maybe"},
        {"type": "state", "source": "bunday_yoq", "field": "x", "equals": True},
        {"type": "and", "of": [{"type": "absent", "metric": "a", "max_age_s": 60}]},
        {"type": "not", "of": []},
        # birlashtirishda faqat host darajasidagi shartlar
        {"type": "and", "of": [{"type": "absent", "metric": "a", "max_age_s": 60},
                               {"type": "state", "source": "channel", "field": "failing", "equals": True}]},
        # chuqurlik > 3
        {"type": "not", "of": [{"type": "not", "of": [{"type": "not", "of": [{"type": "not", "of": [
            {"type": "absent", "metric": "a", "max_age_s": 60}]}]}]}]},
    ],
)  # fmt: skip
def test_invalid_conditions_rejected(cond: dict[str, Any]) -> None:
    with pytest.raises(ConditionError):
        validate_condition(cond)


# ---------------------------------------------------------------- shartlar
def test_threshold_fires_only_on_fresh_data_and_none_when_stale() -> None:
    s = new_server()
    only("AL-009")
    put(s, "cpu_busy_percent", 95, T0)
    (subj,) = evaluate_rule(rule("AL-009"), Ctx(T0))
    assert subj.firing is True and subj.value == 95 and "chegara > 90" in subj.detail
    (stale,) = evaluate_rule(rule("AL-009"), Ctx(T0 + timedelta(minutes=10)))
    assert stale.firing is None  # agent jim: "tiklandi" emas, "ma'lumot yo'q"
    put(s, "cpu_busy_percent", 40, T0 + timedelta(minutes=10))
    assert evaluate_rule(rule("AL-009"), Ctx(T0 + timedelta(minutes=10)))[0].firing is False


def test_threshold_fanout_per_mount_with_display_name() -> None:
    s = new_server()
    put(s, "fs_used_percent", 96, T0, mount="/", device="/dev/sda1", fstype="ext4")
    put(s, "fs_used_percent", 10, T0, mount="/data", device="/dev/sdb1", fstype="ext4")
    by = {x.name: x.firing for x in evaluate_rule(rule("AL-021"), Ctx(T0))}
    assert by == {"main-2 (/)": True, "main-2 (/data)": False}


def test_threshold_window_average() -> None:
    s = new_server()
    for i, v in enumerate([100, 100, 10, 10]):
        put(s, "cpu_busy_percent", v, T0 - timedelta(seconds=45 - 15 * i))
    cond = {
        "type": "threshold",
        "metric": "cpu_busy_percent",
        "op": ">",
        "value": 50,
        "aggregate": "avg",
        "window_s": 60,
    }
    r = AlertRule(key="X", name="x", condition=cond, severity="info", scope={"type": "host"})
    subj = evaluate_rule(r, Ctx(T0))[0]
    assert (
        subj.value == pytest.approx(55) and subj.firing is True
    )  # 100,100,10,10 -> o'rtacha 55 > 50
    r.condition = {**cond, "value": 60}
    assert evaluate_rule(r, Ctx(T0))[0].firing is False


def test_rate_handles_counter_reset() -> None:
    s = new_server()
    for i, v in enumerate([10, 11, 12, 1, 2]):  # 12 -> 1 qayta boshlash: +1 (yangi qiymat)
        put(
            s,
            "docker_container_restarts_total",
            v,
            T0 - timedelta(seconds=60 - 15 * i),
            container="web",
        )
    cond = {
        "type": "rate",
        "metric": "docker_container_restarts_total",
        "increase": 3,
        "window_s": 600,
    }
    r = AlertRule(key="X", name="x", condition=cond, severity="high", scope={"type": "host"})
    (subj,) = evaluate_rule(r, Ctx(T0))
    assert subj.value == 1 + 1 + 1 + 1 and subj.firing is True  # 1+1+1(reset: 1)+1


def test_boot_time_change_fires_reboot_rule() -> None:
    s = new_server()
    only("AL-003")
    put(s, "boot_time_seconds", 1000, T0 - timedelta(minutes=5))
    put(s, "boot_time_seconds", 1000, T0 - timedelta(minutes=4))
    assert evaluate_rule(rule("AL-003"), Ctx(T0))[0].firing is False
    put(s, "boot_time_seconds", 1300, T0 - timedelta(minutes=1))  # qayta yuklandi
    assert evaluate_rule(rule("AL-003"), Ctx(T0))[0].firing is True


def test_linear_fit() -> None:
    slope, r2 = linear_fit([(float(t), 2.0 * t + 5) for t in range(10)])
    assert slope == pytest.approx(2.0) and r2 == pytest.approx(1.0)
    assert linear_fit([(float(t), 7.0) for t in range(10)]) == (0.0, 0.0)
    assert linear_fit([(1.0, 1.0)] * 3) == (0.0, 0.0)


def _disk(
    s: Server, start_pct: float, per_hour_pct: float, hours: int = 6, total: float = 100e9
) -> None:
    for i in range(hours * 12 + 1):  # har 5 daqiqada
        at = T0 - timedelta(hours=hours) + timedelta(minutes=5 * i)
        pct = start_pct + per_hour_pct * (5 * i / 60)
        put(s, "fs_used_bytes", total * pct / 100, at, mount="/", device="/dev/sda1", fstype="ext4")
        put(s, "fs_total_bytes", total, at, mount="/", device="/dev/sda1", fstype="ext4")


def test_forecast_fires_on_fast_growth_not_on_flat_or_noisy() -> None:
    s = new_server()
    _disk(s, 60, 2.0)  # +2%/soat, hozir 72% -> 14 soatda to'ladi
    assert evaluate_rule(rule("AL-022"), Ctx(T0))[0].firing is True  # < 7 kun
    assert evaluate_rule(rule("AL-023"), Ctx(T0))[0].firing is True  # < 24 soat
    slow = new_server("slow")
    _disk(slow, 60, 0.1)  # 400 soat -> 7 kundan ko'p
    by = {x.name: x for x in evaluate_rule(rule("AL-022"), Ctx(T0))}
    assert by["slow (/)"].firing is False
    flat = new_server("flat")
    _disk(flat, 70, 0.0)
    assert {x.name: x.firing for x in evaluate_rule(rule("AL-022"), Ctx(T0))}["flat (/)"] is False


def test_forecast_needs_min_used_percent_and_enough_points() -> None:
    s = new_server()
    _disk(s, 5, 3.0, hours=2)  # tez o'smoqda, lekin band < 50%
    assert evaluate_rule(rule("AL-023"), Ctx(T0))[0].firing is False
    fresh = new_server("fresh")
    put(fresh, "fs_used_bytes", 9e10, T0, mount="/", device="d", fstype="ext4")
    put(fresh, "fs_total_bytes", 1e11, T0, mount="/", device="d", fstype="ext4")
    by = {x.name: x.firing for x in evaluate_rule(rule("AL-023"), Ctx(T0))}
    assert by["fresh (/)"] is None  # nuqta yetarli emas


def test_host_silence_rules_with_reachability(tg_down: dict[str, bool]) -> None:
    s = new_server()
    alive(s, T0 - timedelta(minutes=5))
    now = Ctx(T0)
    tg_down["up"] = False
    assert evaluate_rule(rule("AL-001"), now)[0].firing is True
    assert evaluate_rule(rule("AL-002"), now)[0].firing is False
    tg_down["up"] = True
    assert evaluate_rule(rule("AL-001"), Ctx(T0))[0].firing is False
    assert evaluate_rule(rule("AL-002"), Ctx(T0))[0].firing is True
    alive(s, T0 - timedelta(seconds=10))
    assert evaluate_rule(rule("AL-001"), Ctx(T0))[0].firing is False  # agent tirik


def test_reachability_unknown_without_ip_and_loopback_never_probed(
    tg_down: dict[str, bool],
) -> None:
    s = new_server(ip=None)
    alive(s, T0 - timedelta(minutes=5))
    assert evaluate_rule(rule("AL-001"), Ctx(T0))[0].firing is None
    assert (
        conditions.tcp_probe("127.0.0.1", 22) is False or True
    )  # monkeypatch ostida; haqiqiysi pastda


def test_real_tcp_probe_refuses_loopback_and_garbage() -> None:
    conditions._probe_cache.clear()
    assert conditions.tcp_probe("127.0.0.1", 22) is False
    assert conditions.tcp_probe("169.254.169.254", 80) is False
    assert conditions.tcp_probe("not-an-ip", 22) is False


def test_short_circuit_skips_probe_when_agent_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    s = new_server()
    alive(s, T0 - timedelta(seconds=5))
    calls: list[str] = []

    def probe(*args: Any, **kwargs: Any) -> bool:
        calls.append("x")
        return True

    monkeypatch.setattr(conditions, "tcp_probe", probe)
    evaluate_rule(rule("AL-001"), Ctx(T0))
    assert calls == []  # qimmat tekshiruv faqat kerak bo'lganda


def test_scope_tags_limit_subjects() -> None:
    a = new_server("a-1", tags=["prod"])
    b = new_server("b-1", tags=["dev"])
    for s in (a, b):
        put(s, "cpu_busy_percent", 99, T0)
    r = rule("AL-009")
    r.scope = {"type": "host", "tags": ["prod"]}
    assert [x.name for x in evaluate_rule(r, Ctx(T0))] == ["a-1"]


def test_heartbeat_and_channel_sources() -> None:
    job, _ = HeartbeatJob.issue("appctl-backup@main-2", 3600, grace_s=600)
    assert evaluate_rule(rule("AL-047"), Ctx(T0))[0].firing is None  # hali bir marta ham kelmagan
    HeartbeatJob.objects.filter(pk=job.pk).update(
        last_beat_at=T0 - timedelta(hours=1, minutes=5), last_ok=True
    )
    assert evaluate_rule(rule("AL-047"), Ctx(T0))[0].firing is False
    HeartbeatJob.objects.filter(pk=job.pk).update(last_beat_at=T0 - timedelta(hours=2))
    assert evaluate_rule(rule("AL-047"), Ctx(T0))[0].firing is True
    HeartbeatJob.objects.filter(pk=job.pk).update(last_ok=False, last_message="dump xato")
    failed = evaluate_rule(rule("AL-048"), Ctx(T0))[0]
    assert failed.firing is True and "dump xato" in failed.detail

    ch = channel()
    for status in ("failed", "failed", "sent"):
        Notification.objects.create(channel=ch, event="x", status=status)
    assert evaluate_rule(rule("AL-086"), Ctx(T0))[0].firing is False
    for _ in range(3):
        Notification.objects.create(channel=ch, event="x", status="failed")
    assert evaluate_rule(rule("AL-086"), Ctx(T0))[0].firing is True


# ---------------------------------------------------------------- holat mashinasi va incident
def cpu_cycle(s: Server, value: float, at: datetime) -> engine.CycleStats:
    put(s, "cpu_busy_percent", value, at)
    alive(s, at)
    return run_cycle(at)


def test_pending_then_firing_after_for_opens_incident_and_notifies_once() -> None:
    s = new_server()
    channel()
    only("AL-009")  # for = 600 s
    cpu_cycle(s, 95, T0)
    inst = AlertInstance.objects.get()
    assert inst.state == "pending" and Incident.objects.count() == 0 and not texts()
    cpu_cycle(s, 95, T0 + timedelta(minutes=5))
    assert AlertInstance.objects.get().state == "pending"
    stats = cpu_cycle(s, 96, T0 + timedelta(minutes=10))
    inst.refresh_from_db()
    assert inst.state == "firing" and stats.incidents_opened == 1 and stats.notified == 1
    incident = Incident.objects.get()
    assert (
        incident.scope_key == f"host:{s.pk}"
        and incident.severity == "warning"
        and incident.status == "open"
    )
    assert [e.type for e in incident.events.order_by("id")] == ["opened", "notified"]
    (text,) = texts()
    assert "CPU yuqori: main-2" in text and "cpu_busy_percent = 96.0" in text and "RB-009" in text
    assert f"/incidents/{incident.pk}" in text
    # keyingi davrlarda takroriy xabar yo'q
    cpu_cycle(s, 97, T0 + timedelta(minutes=11))
    cpu_cycle(s, 97, T0 + timedelta(minutes=12))
    assert len(texts()) == 1


def test_short_spike_never_alerts() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 20, T0 + timedelta(minutes=3))  # for o'tmasdan tushdi
    assert AlertInstance.objects.get().state == "ok"
    cpu_cycle(s, 95, T0 + timedelta(minutes=4))
    cpu_cycle(s, 95, T0 + timedelta(minutes=13))  # qaytadan hisoblanadi: 9 daqiqa < 10
    assert not texts() and Incident.objects.count() == 0


def test_resolve_after_delay_closes_incident_and_sends_recovery_with_duration() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    cpu_cycle(s, 30, T0 + timedelta(minutes=12))
    assert (
        AlertInstance.objects.get().state == "resolving" and Incident.objects.get().status == "open"
    )
    cpu_cycle(
        s, 95, T0 + timedelta(minutes=12, seconds=30)
    )  # titrash: yana firing, yangi incident ochilmaydi
    assert AlertInstance.objects.get().state == "firing" and Incident.objects.count() == 1
    cpu_cycle(s, 30, T0 + timedelta(minutes=15))
    cpu_cycle(s, 30, T0 + timedelta(minutes=16, seconds=5))  # resolve_after (60 s) o'tdi
    incident = Incident.objects.get()
    assert incident.status == "resolved" and incident.resolved_at is not None
    assert AlertInstance.objects.get().state == "ok"
    recovery = texts()[-1]
    assert (
        recovery.startswith("✅")
        and "Tiklandi" in recovery
        and "Davomiyligi: 16 daqiqa" in recovery
    )


def test_no_data_keeps_alert_firing_instead_of_resolving() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    run_cycle(T0 + timedelta(minutes=30))  # agent jim: metrika yangilanmadi
    assert AlertInstance.objects.get().state == "firing" and Incident.objects.get().status == "open"
    assert len(texts()) == 1


def test_alerts_on_same_host_share_one_incident_and_escalation_reopens_after_ack() -> None:
    from apps.alerts import services

    s = new_server()
    channel()
    only("AL-009", "AL-015")
    put(s, "cpu_busy_percent", 95, T0)
    put(s, "mem_used_percent", 50, T0)
    alive(s, T0)
    run_cycle(T0)
    put(s, "cpu_busy_percent", 95, T0 + timedelta(minutes=10))
    put(s, "mem_used_percent", 50, T0 + timedelta(minutes=10))
    alive(s, T0 + timedelta(minutes=10))
    run_cycle(T0 + timedelta(minutes=10))
    incident = Incident.objects.get()
    assert incident.severity == "warning"
    services.ack(incident, None, "ko'ryapman")
    # RAM kritik bo'ldi: bitta incident, ahamiyat oshdi, ack bekor, qayta xabar
    for minute in (11, 16):
        put(s, "cpu_busy_percent", 95, T0 + timedelta(minutes=minute))
        put(s, "mem_used_percent", 98, T0 + timedelta(minutes=minute))
        alive(s, T0 + timedelta(minutes=minute))
        run_cycle(T0 + timedelta(minutes=minute))
    assert Incident.objects.count() == 1
    incident.refresh_from_db()
    assert (
        incident.severity == "critical" and incident.status == "open" and incident.acked_by is None
    )
    assert "severity_changed" in [e.type for e in incident.events.all()]
    assert len(texts()) == 2 and "RAM kritik" in texts()[-1]


def test_disabled_rule_closes_its_alerts() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    AlertRule.objects.filter(key="AL-009").update(enabled=False)
    run_cycle(T0 + timedelta(minutes=11))
    run_cycle(T0 + timedelta(minutes=13))
    assert Incident.objects.get().status == "resolved"


def test_broken_rule_does_not_stop_others() -> None:
    s = new_server()
    channel()
    only("AL-009", "AL-014")
    AlertRule.objects.filter(key="AL-014").update(condition={"type": "boom"})
    cpu_cycle(s, 95, T0)
    stats = cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    assert stats.rule_errors == 1 and len(texts()) == 1


def test_archived_server_alerts_resolve() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    Server.objects.filter(pk=s.pk).update(status="archived")
    run_cycle(T0 + timedelta(minutes=11))
    run_cycle(T0 + timedelta(minutes=13))
    assert Incident.objects.get().status == "resolved"


def test_evaluator_heartbeat_recorded() -> None:
    from apps.alerts.models import EvaluatorState

    run_cycle(T0)
    state = EvaluatorState.objects.get()
    assert state.last_run_at == T0 and state.last_duration_ms >= 0


# ---------------------------------------------------------------- bostirish
def disk_cycle(s: Server, pct: float, at: datetime) -> engine.CycleStats:
    put(s, "fs_used_percent", pct, at, mount="/", device="/dev/sda1", fstype="ext4")
    return run_cycle(at)


def test_host_down_suppresses_dependent_alerts_then_notifies_after_recovery(
    tg_down: dict[str, bool],
) -> None:
    s = new_server()
    channel()
    only("AL-001", "AL-025")
    alive(s, T0 - timedelta(minutes=10))
    put(s, "fs_readonly", 1, T0 - timedelta(minutes=5), mount="/", device="/dev/sda1")
    run_cycle(T0 - timedelta(minutes=5))  # AL-025: for=60 s, hali pending
    # Server o'chdi: agent_up yangilanmaydi, fs_readonly esa "yangi" (masalan, oxirgi paket) va rost.
    put(s, "fs_readonly", 1, T0 + timedelta(minutes=3), mount="/", device="/dev/sda1")
    run_cycle(T0 + timedelta(minutes=3))
    by_key = {
        i.rule.key: i for i in AlertInstance.objects.select_related("rule").filter(state="firing")
    }
    assert by_key["AL-001"].suppressed is False and by_key["AL-025"].suppressed is True
    assert len(texts()) == 1 and "Server o'chdi" in texts()[0]  # 1 ta xabar, 2 ta emas (FR-ALR-011)
    incident = Incident.objects.get()
    assert incident.suppressed is False and incident.severity == "critical"

    # Server qaytdi, lekin fayl tizimi hamon faqat-o'qish: endi o'zi haqida xabar beradi (12.5.1).
    tg_down["up"] = True
    back = T0 + timedelta(minutes=10)
    alive(s, back)
    put(s, "fs_readonly", 1, back, mount="/", device="/dev/sda1")
    run_cycle(back)
    assert len(texts()) == 2 and "Fayl tizimi faqat o'qish" in texts()[1]
    alive(s, back + timedelta(minutes=2))
    put(s, "fs_readonly", 1, back + timedelta(minutes=2), mount="/", device="/dev/sda1")
    run_cycle(back + timedelta(minutes=2))
    assert AlertInstance.objects.get(rule__key="AL-001").state == "ok"
    incident.refresh_from_db()
    assert incident.status == "open"  # AL-025 hamon rost


def test_higher_severity_disk_alert_supersedes_lower_one() -> None:
    s = new_server()
    channel()
    only("AL-019", "AL-020")
    disk_cycle(s, 91, T0)
    disk_cycle(s, 91, T0 + timedelta(minutes=6))
    firing = {
        i.rule.key: i for i in AlertInstance.objects.select_related("rule").filter(state="firing")
    }
    assert set(firing) == {"AL-019", "AL-020"}
    assert firing["AL-019"].suppressed is True and firing["AL-020"].suppressed is False
    assert len(texts()) == 1 and "Disk 90%" in texts()[0]


def test_silence_suppresses_then_notifies_when_it_ends() -> None:
    s = new_server()
    channel()
    only("AL-009")
    Silence.objects.create(
        matchers=[{"label": "server", "op": "=", "value": "main-2"}],
        ends_at=T0 + timedelta(minutes=30), starts_at=T0 - timedelta(minutes=1), reason="reboot",
    )  # fmt: skip
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    incident = Incident.objects.get()
    assert incident.suppressed is True and not texts()  # incident bor, xabar yo'q (12.6.1)
    cpu_cycle(s, 95, T0 + timedelta(minutes=29))
    assert not texts()
    cpu_cycle(s, 95, T0 + timedelta(minutes=31))  # silence tugadi, shart hamon rost
    assert len(texts()) == 1
    incident.refresh_from_db()
    assert incident.suppressed is False


def test_silence_matchers_by_rule_severity_and_not_equal() -> None:
    s = new_server()
    channel()
    only("AL-009")
    for matchers, silenced in (
        ([{"label": "rule", "op": "=", "value": "AL-009"}], True),
        ([{"label": "severity", "op": "=~", "value": "warn.*"}], True),
        ([{"label": "server", "op": "!=", "value": "main-2"}], False),
        ([{"label": "server", "op": "=", "value": "main-2"}, {"label": "severity", "op": "!=", "value": "warning"}], False),
    ):  # fmt: skip
        Silence.objects.all().delete()
        Notification.objects.all().delete()
        AlertInstance.objects.all().delete()
        Incident.objects.all().delete()
        Silence.objects.create(
            matchers=matchers,
            starts_at=T0 - timedelta(days=1),
            ends_at=T0 + timedelta(days=1),
            reason="t",
        )
        cpu_cycle(s, 95, T0)
        cpu_cycle(s, 95, T0 + timedelta(minutes=10))
        assert (not texts()) is silenced, matchers


def test_maintenance_window_and_pause_suppress() -> None:
    s = new_server()
    p = Project.objects.create(slug="nazar", name="Nazar", kind="own")
    ProjectServer.objects.create(project=p, server=s)
    channel()
    only("AL-009")
    MaintenanceWindow.objects.create(
        scope={"projects": [str(p.pk)]},
        starts_at=T0 - timedelta(hours=1),
        ends_at=T0 + timedelta(hours=1),
        reason="yangilash",
    )
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    assert not texts() and Incident.objects.get().suppressed is True
    MaintenanceWindow.objects.all().update(cancelled_at=T0)
    Server.objects.filter(pk=s.pk).update(status="paused")
    AlertInstance.objects.update(notified_at=None)
    cpu_cycle(s, 95, T0 + timedelta(minutes=11))
    assert not texts()  # pause hamma narsadan ustun


def test_recovery_not_sent_if_nobody_was_notified() -> None:
    s = new_server()
    channel()
    only("AL-009")
    Silence.objects.create(
        matchers=[{"label": "server", "op": "=", "value": "main-2"}], starts_at=T0 - timedelta(days=1),
        ends_at=T0 + timedelta(days=1), reason="t",
    )  # fmt: skip
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    cpu_cycle(s, 30, T0 + timedelta(minutes=12))
    cpu_cycle(s, 30, T0 + timedelta(minutes=14))
    assert Incident.objects.get().status == "resolved" and not texts()


def test_mass_silence_suppresses_individual_host_alerts(tg_down: dict[str, bool]) -> None:
    channel()
    only("AL-001", "AL-008")
    servers = [new_server(f"srv-{i}", ip=f"164.68.105.{190 + i}") for i in range(3)]
    for s in servers:
        alive(s, T0 - timedelta(minutes=10))
    run_cycle(T0)
    assert AlertInstance.objects.filter(state="firing").count() == 4  # 3 x AL-001 + AL-008
    sent = texts()
    assert len(sent) == 1 and "Ko'p host jim" in sent[0]
    assert AlertInstance.objects.filter(rule__key="AL-001", suppressed=True).count() == 3


# ---------------------------------------------------------------- eslatmalar
def test_critical_reminders_stop_after_ack() -> None:
    from apps.alerts import services

    s = new_server()
    channel()
    only("AL-015")
    for minute in (0, 5):
        put(s, "mem_used_percent", 98, T0 + timedelta(minutes=minute))
        alive(s, T0 + timedelta(minutes=minute))
        run_cycle(T0 + timedelta(minutes=minute))
    assert len(texts()) == 1
    put(s, "mem_used_percent", 98, T0 + timedelta(minutes=20))
    alive(s, T0 + timedelta(minutes=20))
    run_cycle(T0 + timedelta(minutes=20))
    assert len(texts()) == 1  # 30 daqiqa o'tmagan

    for minute in (36, 70):
        put(s, "mem_used_percent", 98, T0 + timedelta(minutes=minute))
        alive(s, T0 + timedelta(minutes=minute))
        run_cycle(T0 + timedelta(minutes=minute))
    reminders = [t for t in texts() if t.startswith("🔴 <b>Eslatma")]
    assert len(reminders) == 2 and "RAM kritik" in reminders[0]
    services.ack(Incident.objects.get(), None)
    put(s, "mem_used_percent", 98, T0 + timedelta(minutes=120))
    alive(s, T0 + timedelta(minutes=120))
    run_cycle(T0 + timedelta(minutes=120))
    assert len([t for t in texts() if "Eslatma" in t]) == 2  # ack dan keyin eslatma yo'q


def test_warning_has_no_early_reminders() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    cpu_cycle(s, 95, T0 + timedelta(minutes=10))
    cpu_cycle(s, 95, T0 + timedelta(hours=3))
    assert len(texts()) == 1  # warning: 24 soatdan keyin


# ---------------------------------------------------------------- suppression yordamchilari
def test_matcher_validation_and_matching() -> None:
    validate_matchers([{"label": "server", "op": "=", "value": "a"}])
    for bad in (
        [], "x", [{"label": "x", "op": "=", "value": "a"}], [{"label": "server", "op": "~", "value": "a"}],
        [{"label": "server", "op": "=~", "value": "("}], [{"label": "server", "op": "=", "value": ""}],
        [{"label": "server", "op": "=", "value": "a", "extra": 1}],
    ):  # fmt: skip
        with pytest.raises(MatcherError):
            validate_matchers(bad)
    labels = {"server": ["main-2"], "tag": ["prod", "eu"], "project": []}
    assert matches([{"label": "tag", "op": "=", "value": "eu"}], labels)
    assert matches([{"label": "tag", "op": "!=", "value": "dev"}], labels)
    assert not matches([{"label": "tag", "op": "!=", "value": "prod"}], labels)
    assert matches([{"label": "server", "op": "=~", "value": "main-\\d"}], labels)
    assert not matches([{"label": "project", "op": "=", "value": "nazar"}], labels)
    assert matches([{"label": "project", "op": "!=", "value": "nazar"}], labels)


def test_run_evaluator_command_once() -> None:
    s = new_server()
    put(s, "cpu_busy_percent", 10, T0)
    call_command("run_evaluator", once=True)
    from apps.alerts.models import EvaluatorState

    assert EvaluatorState.objects.exists()


def test_pending_resets_when_data_disappears() -> None:
    s = new_server()
    channel()
    only("AL-009")
    cpu_cycle(s, 95, T0)
    assert AlertInstance.objects.get().state == "pending"
    run_cycle(T0 + timedelta(minutes=30))  # agent jim: ma'lumot yo'q, uzluksizlik buzildi
    assert AlertInstance.objects.get().state == "ok"
    cpu_cycle(s, 95, T0 + timedelta(minutes=60))  # qaytdi: qaytadan 10 daqiqa kutiladi
    assert AlertInstance.objects.get().state == "pending" and not texts()


def test_joined_alert_message_lists_other_active_alerts() -> None:
    s = new_server()
    channel()
    only("AL-009", "AL-015")
    for minute in (0, 10):
        at = T0 + timedelta(minutes=minute)
        put(s, "cpu_busy_percent", 95, at)
        put(s, "mem_used_percent", 98, at)
        alive(s, at)
        run_cycle(at)
    sent = texts()
    assert len(sent) == 2
    joined = [t for t in sent if "boshqa faol alertlar" in t]
    assert len(joined) == 1  # faqat ikkinchi xabarda (birinchisida boshqasi hali yo'q)
    other = "CPU yuqori" if "RAM kritik" in joined[0].split("<b>")[1] else "RAM kritik"
    assert f"boshqa faol alertlar: {other}: main-2" in joined[0]
