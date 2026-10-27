"""Metrikalar so'rovi API (B4, TZ 9.5) + server konteynerlari va fayl tizimlari (TZ 9.3)."""

from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.registry.models import Server

from .test_accounts import csrf_client, login, make_user
from .test_alerts import new_server, put

pytestmark = pytest.mark.django_db


@pytest.fixture
def viewer() -> Client:
    make_user("kuzatuvchi", "viewer")
    c = csrf_client()
    login(c, "kuzatuvchi")
    return c


def iso(dt: Any) -> str:
    return str(dt.isoformat().replace("+00:00", "Z"))


def span(minutes: int = 60) -> tuple[Any, Any, str]:
    end = timezone.now()
    start = end - timedelta(minutes=minutes)
    return start, end, f"from={iso(start)}&to={iso(end)}"


def seed(
    server: Server, name: str = "cpu_busy_percent", values: list[float] | None = None, **labels: str
) -> None:
    now = timezone.now()
    values = values if values is not None else [10.0, 20.0, 30.0, 40.0]
    for i, v in enumerate(values):
        put(server, name, v, now - timedelta(seconds=15 * (len(values) - i)), **labels)


# ---------------------------------------------------------------- query
def test_query_returns_points_unit_and_source(viewer: Client) -> None:
    s = new_server()
    seed(s)
    _, _, q = span()
    body = viewer.get(f"/api/v1/metrics/query?server_id={s.pk}&name=cpu_busy_percent&{q}").json()
    assert body["name"] == "cpu_busy_percent" and body["unit"] == "%" and body["source"] == "raw"
    (series,) = body["series"]
    assert series["labels"] == {} and [p[1] for p in series["points"]] == [10.0, 20.0, 30.0, 40.0]
    assert body["step_seconds"] >= 1


def test_query_filters_by_labels_and_returns_one_series_each(viewer: Client) -> None:
    s = new_server()
    seed(s, "fs_used_percent", [50.0, 51.0], mount="/", device="d1", fstype="ext4")
    seed(s, "fs_used_percent", [10.0, 11.0], mount="/data", device="d2", fstype="ext4")
    _, _, q = span()
    both = viewer.get(f"/api/v1/metrics/query?server_id={s.pk}&name=fs_used_percent&{q}").json()[
        "series"
    ]
    assert {x["labels"]["mount"] for x in both} == {"/", "/data"}
    one = viewer.get(
        f"/api/v1/metrics/query?server_id={s.pk}&name=fs_used_percent&labels[mount]=/data&{q}"
    ).json()["series"]
    assert [x["labels"]["mount"] for x in one] == ["/data"]
    none = viewer.get(
        f"/api/v1/metrics/query?server_id={s.pk}&name=fs_used_percent&labels[mount]=/yoq&{q}"
    ).json()["series"]
    assert none == []


def test_query_step_and_agg_and_null_gaps(viewer: Client) -> None:
    s = new_server()
    now = timezone.now()
    for minutes_ago, v in ((50, 1.0), (49, 3.0), (20, 5.0), (19, 7.0)):  # 29 daqiqalik bo'shliq
        put(s, "load1", v, now - timedelta(minutes=minutes_ago))
    start = now - timedelta(minutes=55)
    q = f"server_id={s.pk}&name=load1&from={iso(start)}&to={iso(now)}"
    stepped = viewer.get(f"/api/v1/metrics/query?{q}&step=60&agg=max").json()
    points = stepped["series"][0]["points"]
    assert stepped["step_seconds"] == 60
    values = [p[1] for p in points]
    assert None in values  # bo'shliq null bilan (grafikda uzilish)
    assert max(v for v in values if v is not None) == 7.0 and 3.0 in values
    times = [p[0] for p in points]
    assert times == sorted(times)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "server_id=yomon&name=cpu_busy_percent",
        "server_id={sid}&name=BAD NAME",
        "server_id={sid}&name=cpu_busy_percent",  # from/to yo'q
        "server_id={sid}&name=cpu_busy_percent&from=2026-01-01&to=2026-01-02",  # zonasiz
        "server_id={sid}&name=cpu_busy_percent&from={end}&to={start}",  # teskari
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={end}&max_points=5",
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={end}&max_points=99999",
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={end}&max_points=abc",
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={end}&step=0",
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={end}&step=1",  # 3600 nuqta > 2000
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={end}&agg=median",
        "server_id={sid}&name=cpu_busy_percent&from={far}&to={end}",  # > 400 kun
        "server_id={sid}&name=cpu_busy_percent&from={start}&to={future}",
    ],
)
def test_query_validation(viewer: Client, query: str) -> None:
    s = new_server()
    start, end, _ = span()
    filled = query.format(
        sid=s.pk,
        start=iso(start),
        end=iso(end),
        future=iso(end + timedelta(hours=2)),
        far=iso(end - timedelta(days=500)),
    )
    response = viewer.get(f"/api/v1/metrics/query?{filled}")
    assert response.status_code == 400 and response.json()["error"]["code"] == "validation_error", (
        filled
    )


def test_query_requires_login_and_known_server() -> None:
    assert Client().get("/api/v1/metrics/query").status_code in (401, 403)
    assert Client().get("/api/v1/metrics/latest").status_code in (401, 403)


def test_query_chooses_aggregate_table_for_long_ranges(viewer: Client) -> None:
    s = new_server()
    seed(s)
    end = timezone.now()
    q = f"server_id={s.pk}&name=cpu_busy_percent&from={iso(end - timedelta(days=2))}&to={iso(end)}"
    assert viewer.get(f"/api/v1/metrics/query?{q}").json()["source"] == "1m"  # TZ 8.4.3: <= 3 kun
    q = f"server_id={s.pk}&name=cpu_busy_percent&from={iso(end - timedelta(days=10))}&to={iso(end)}"
    assert viewer.get(f"/api/v1/metrics/query?{q}").json()["source"] == "5m"


# ---------------------------------------------------------------- latest, names, top
def test_latest_values_per_series(viewer: Client) -> None:
    s = new_server()
    seed(s, "cpu_busy_percent", [10.0, 42.0])
    seed(s, "fs_used_percent", [70.0], mount="/", device="d", fstype="ext4")
    body = viewer.get(
        f"/api/v1/metrics/latest?server_id={s.pk}&names=cpu_busy_percent,fs_used_percent,load1"
    ).json()
    assert body["metrics"]["cpu_busy_percent"][0]["value"] == 42.0
    assert body["metrics"]["fs_used_percent"][0]["labels"]["mount"] == "/"
    assert body["metrics"]["load1"] == []  # yo'q metrika bo'sh ro'yxat
    for bad in ("", "&names=", f"&names={','.join(['a'] * 51)}", "&names=BAD"):
        assert viewer.get(f"/api/v1/metrics/latest?server_id={s.pk}{bad}").status_code == 400


def test_names_list_with_label_keys(viewer: Client) -> None:
    s = new_server()
    other = new_server("core-1", ip="1.1.1.1")
    seed(s, "cpu_busy_percent")
    seed(s, "fs_used_percent", [1.0], mount="/", device="d", fstype="ext4")
    seed(other, "load1", [1.0])
    items = {i["name"]: i for i in viewer.get("/api/v1/metrics/names").json()["items"]}
    assert set(items) == {"cpu_busy_percent", "fs_used_percent", "load1"}
    assert (
        items["fs_used_percent"]["label_keys"] == ["device", "fstype", "mount"]
        and items["cpu_busy_percent"]["unit"] == "%"
    )
    only = {
        i["name"] for i in viewer.get(f"/api/v1/metrics/names?server_id={other.pk}").json()["items"]
    }
    assert only == {"load1"}
    assert viewer.get("/api/v1/metrics/names?server_id=yomon").status_code == 400


def test_top_orders_by_value_and_ignores_stale_or_archived(viewer: Client) -> None:
    a, b, c, old = (
        new_server(n, ip=f"1.1.1.{i}") for i, n in enumerate(["a-1", "b-1", "c-1", "old-1"])
    )
    for s, v in ((a, 30.0), (b, 90.0), (c, 60.0)):
        seed(s, "cpu_busy_percent", [v])
    put(old, "cpu_busy_percent", 99.0, timezone.now() - timedelta(hours=1))  # eskirgan
    Server.objects.filter(pk=c.pk).update(status="archived")
    items = viewer.get("/api/v1/metrics/top?metric=cpu_busy_percent&limit=5").json()["items"]
    assert [(i["server"], i["value"]) for i in items] == [("b-1", 90.0), ("a-1", 30.0)]
    assert len(viewer.get("/api/v1/metrics/top?limit=1").json()["items"]) == 1
    for bad in ("limit=0", "limit=51", "limit=x", "metric=BAD"):
        assert viewer.get(f"/api/v1/metrics/top?{bad}").status_code == 400


# ---------------------------------------------------------------- server sahifasi
def container(s: Server, name: str, values: dict[str, float], age_min: int = 0) -> None:
    at = timezone.now() - timedelta(minutes=age_min)
    for metric, v in values.items():
        put(
            s,
            f"docker_container_{metric}",
            v,
            at,
            container=name,
            project="nazar",
            service=name.split("-")[1],
        )


def test_server_containers(viewer: Client) -> None:
    s = new_server()
    container(
        s,
        "nazar-web-1",
        {
            "running": 1,
            "restarts_total": 2,
            "uptime_seconds": 3600,
            "health": 1,
            "oom_killed": 0,
            "expected": 1,
        },
    )
    container(s, "nazar-db-1", {"running": 0, "restarts_total": 0, "expected": 1}, age_min=30)
    items = viewer.get(f"/api/v1/servers/{s.pk}/containers").json()["items"]
    assert [c["container"] for c in items] == ["nazar-db-1", "nazar-web-1"]
    web, db = items[1], items[0]
    assert (
        web["running"] is True
        and web["restarts"] == 2
        and web["uptime_seconds"] == 3600
        and web["health"] == 1
        and web["stale"] is False
    )
    assert web["project"] == "nazar" and web["service"] == "web"
    assert db["running"] is False and db["stale"] is True  # 30 daqiqa jim
    assert (
        viewer.get("/api/v1/servers/00000000-0000-7000-8000-000000000000/containers").status_code
        == 404
    )


def test_server_filesystems_with_forecast(viewer: Client) -> None:
    s = new_server()
    now = timezone.now()
    total = 100e9
    for i in range(6 * 12 + 1):  # 6 soat, har 5 daqiqada, soatiga +2% (60% dan boshlab)
        at = now - timedelta(hours=6) + timedelta(minutes=5 * i)
        used = total * (0.60 + 0.02 * (5 * i / 60))
        lbl = {"mount": "/", "device": "/dev/sda1", "fstype": "ext4"}
        put(s, "fs_used_bytes", used, at, **lbl)
        put(s, "fs_total_bytes", total, at, **lbl)
        put(s, "fs_used_percent", 100 * used / total, at, **lbl)
        put(s, "fs_readonly", 0, at, mount="/", device="/dev/sda1")
    put(s, "fs_used_bytes", 1e9, now, mount="/boot", device="/dev/sda2", fstype="ext4")
    put(s, "fs_total_bytes", 1e10, now, mount="/boot", device="/dev/sda2", fstype="ext4")
    items = {
        m["mount"]: m for m in viewer.get(f"/api/v1/servers/{s.pk}/filesystems").json()["items"]
    }
    root = items["/"]
    assert (
        root["device"] == "/dev/sda1"
        and root["readonly"] is False
        and 71 < root["used_percent"] < 73.5
    )
    assert 12 <= root["days_until_full"] * 24 <= 16  # ~28% / (2%/soat) ≈ 14 soat
    assert items["/boot"]["days_until_full"] is None  # bashorat uchun nuqta yetmaydi
    assert (
        viewer.get("/api/v1/servers/00000000-0000-7000-8000-000000000000/filesystems").status_code
        == 404
    )
