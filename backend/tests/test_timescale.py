"""TimescaleDB sinovlari (R-102, TZ 8.4): agregatlar, siyosatlar, so'rov marshrutizatsiyasi.

`refresh_continuous_aggregate` tranzaksiya ichida ishlamaydi, shuning uchun `transaction=True`.
Seriya identifikatorlari har testda yangi; testlar bir-biridan faqat series_id bo'yicha ajraladi.
"""

from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.metrics.models import Series
from apps.metrics.query import pick_source, run_query
from apps.registry.models import Server

pytestmark = pytest.mark.django_db(transaction=True)


def sql(statement: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


def make_series(server: Server, name: str, *, rollup: bool, tag: str = "x") -> Series:
    return Series.objects.create(server=server, name=name, labels_hash=tag, rollup=rollup)


def fill(
    series_id: int, start: str, end: str, value: str = "5.0", step: str = "15 seconds"
) -> None:
    """[start, end) oralig'iga `step` qadam bilan namunalar yozadi (vaqtlar SQL ifodasi)."""
    sql(
        f"""INSERT INTO metric_samples
            SELECT t, %s, ({value})::double precision
            FROM generate_series({start}, {end} - interval '1 second', interval '{step}') t""",  # noqa: S608
        [series_id],
    )


def refresh(window_start: str, window_end: str) -> None:
    """Ierarxiya tartibida: 1m -> 5m -> 1h."""
    for view in ("metric_1m", "metric_5m", "metric_1h"):
        sql(f"CALL refresh_continuous_aggregate('{view}', {window_start}, {window_end})")  # noqa: S608


@pytest.fixture
def server(db: None) -> Server:
    return Server.objects.create(name="ts-test")


def test_hypertable_compression_retention_and_cagg_policies_exist(server: Server) -> None:
    hypertables = {
        r[0] for r in sql("SELECT hypertable_name FROM timescaledb_information.hypertables")
    }
    assert "metric_samples" in hypertables

    jobs = sql(
        """SELECT hypertable_name, proc_name FROM timescaledb_information.jobs
           WHERE proc_name IN ('policy_compression', 'policy_retention',
                               'policy_refresh_continuous_aggregate')
             AND hypertable_name NOT IN ('probe_results', 'dns_results')"""
    )
    procs = [proc for _, proc in jobs]
    assert procs.count("policy_compression") == 1
    assert procs.count("policy_retention") == 4  # xom + 1m + 5m + 1h
    assert procs.count("policy_refresh_continuous_aggregate") == 3

    caggs = {
        r[0] for r in sql("SELECT view_name FROM timescaledb_information.continuous_aggregates")
    }
    assert {"metric_1m", "metric_5m", "metric_1h"} <= caggs


def test_hierarchical_aggregates_match_raw(server: Server) -> None:
    """1m, 5m, 1h yig'indisi va soni xom ma'lumot bilan bir xil (T-U-DAT-01, T-U-DAT-02)."""
    series = make_series(server, "cpu_busy_percent", rollup=True)
    base = "date_trunc('hour', now())"
    fill(
        series.id,
        f"{base} - interval '4 hours'",
        f"{base} - interval '1 hour'",
        value="mod(extract(epoch FROM t)::bigint, 100)",
    )
    refresh("now() - interval '6 hours'", "now() - interval '30 minutes'")

    raw = sql("SELECT sum(value), count(*) FROM metric_samples WHERE series_id = %s", [series.id])[
        0
    ]
    assert raw[1] == 720
    for view in ("metric_1m", "metric_5m", "metric_1h"):
        got = sql(f"SELECT sum(v_sum), sum(n) FROM {view} WHERE series_id = %s", [series.id])[0]  # noqa: S608
        assert float(got[0]) == pytest.approx(raw[0]), view
        assert int(got[1]) == 720, view
    # 1m da har daqiqada 4 namuna (15 s qadam)
    assert sql("SELECT min(n), max(n) FROM metric_1m WHERE series_id = %s", [series.id])[0] == (
        4,
        4,
    )


def test_only_rollup_series_are_aggregated(server: Server) -> None:
    """R-102: agregat faqat `rollup=true` seriyalar uchun (JOIN li agregat 2.17.2 da ishlaydi)."""
    yes = make_series(server, "cpu_busy_percent", rollup=True, tag="a")
    no = make_series(server, "docker_container_cpu_percent", rollup=False, tag="b")
    base = "date_trunc('hour', now())"
    for s in (yes, no):
        fill(s.id, f"{base} - interval '3 hours'", f"{base} - interval '2 hours'")
    refresh("now() - interval '5 hours'", "now() - interval '30 minutes'")

    for view in ("metric_1m", "metric_5m", "metric_1h"):
        ids = {r[0] for r in sql(f"SELECT DISTINCT series_id FROM {view}")}  # noqa: S608
        assert yes.id in ids, view
        assert no.id not in ids, view
    assert sql("SELECT count(*) FROM metric_samples WHERE series_id = %s", [no.id])[0][0] == 240


def test_pick_source_thresholds() -> None:
    assert pick_source(timedelta(hours=6)) == "raw"
    assert pick_source(timedelta(hours=6, seconds=1)) == "1m"
    assert pick_source(timedelta(days=3)) == "1m"
    assert pick_source(timedelta(days=3, seconds=1)) == "5m"
    assert pick_source(timedelta(days=30)) == "5m"
    assert pick_source(timedelta(days=30, seconds=1)) == "1h"


def test_run_query_routes_to_the_right_table_and_downsamples(server: Server) -> None:
    series = make_series(server, "cpu_busy_percent", rollup=True)
    fill(series.id, "now() - interval '13 hours'", "now() - interval '1 hour'")
    refresh("now() - interval '14 hours'", "now() - interval '30 minutes'")
    end = timezone.now() - timedelta(minutes=30)

    source, step, points = run_query(series.id, end - timedelta(hours=2), end, max_points=1000)
    assert source == "raw" and step == 8  # 7200 s / 1000 nuqta
    assert 0 < len(points) <= 1000

    source, step, points = run_query(series.id, end - timedelta(hours=11), end, max_points=1000)
    assert source == "1m" and step == 60
    assert 0 < len(points) <= 1000
    assert all(v == pytest.approx(5.0) for _, v in points)

    source, _, points = run_query(series.id, end - timedelta(hours=11), end, max_points=100)
    assert source == "1m" and len(points) <= 100  # siyraklash (max_points)


def test_run_query_rejects_unknown_aggregation(server: Server) -> None:
    series = make_series(server, "load1", rollup=True)
    now = timezone.now()
    with pytest.raises(ValueError):
        run_query(series.id, now - timedelta(hours=1), now, agg="drop table")


def test_query_endpoint(client: Client, settings: Any, server: Server) -> None:
    settings.DEBUG = True  # pytest-django DEBUG ni o'chiradi; prototip endpointlar faqat DEBUG da
    series = make_series(server, "fs_used_percent", rollup=True)
    series.labels = {"mount": "/"}
    series.unit = "%"
    series.save()
    fill(series.id, "now() - interval '20 minutes'", "now()", value="42")
    now = timezone.now()
    params = {
        "server_id": str(server.id),
        "name": "fs_used_percent",
        "from": (now - timedelta(minutes=30)).isoformat(),
        "to": now.isoformat(),
        "labels[mount]": "/",
    }
    data = client.get("/proto/api/query", params).json()
    assert data["source"] == "raw" and data["unit"] == "%"
    assert len(data["series"]) == 1 and data["series"][0]["labels"] == {"mount": "/"}
    assert all(v == 42 for _, v in data["series"][0]["points"])

    assert (
        client.get("/proto/api/query", {**params, "labels[mount]": "/boshqa"}).json()["series"]
        == []
    )
    assert client.get("/proto/api/query", {"server_id": "x"}).status_code == 400
    names = client.get("/proto/api/names", {"server_id": str(server.id)}).json()
    assert names["items"][0]["name"] == "fs_used_percent"
    assert client.get("/proto/api/servers").json()["items"][0]["name"] == "ts-test"
    assert client.get("/proto/").status_code == 200


def test_prototype_endpoints_are_closed_outside_debug(
    client: Client, settings: Any, server: Server
) -> None:
    settings.DEBUG = False
    for url in ("/proto/", "/proto/api/servers", "/proto/api/names", "/proto/api/query"):
        assert client.get(url).status_code == 404, url


def test_duplicate_into_compressed_chunk_is_not_deduplicated(server: Server) -> None:
    """Xarakterlovchi test (R-102, TZ 8.4.1): siqilgan bo'lakda UNIQUE indeks takrorni to'smaydi.

    Shuning uchun ingest 1 soatdan eski namunani yozmaydi (`MAX_SAMPLE_AGE_S`). Agar TimescaleDB
    yangilanishida bu xatti-harakat o'zgarsa, test yiqiladi va TZ 8.4.1 qayta ko'rib chiqiladi.
    """
    series = make_series(server, "load1", rollup=True)
    old = "now() - interval '5 days'"
    fill(series.id, old, f"{old} + interval '10 minutes'", value="1.0")
    sql("""SELECT compress_chunk(c, if_not_compressed => true)
           FROM show_chunks('metric_samples', older_than => now() - interval '3 days') c""")
    before = sql("SELECT count(*) FROM metric_samples WHERE series_id = %s", [series.id])[0][0]
    sql(
        f"""INSERT INTO metric_samples
            SELECT t, %s, 2.0
            FROM generate_series({old}, {old} + interval '10 minutes' - interval '1 second',
                                 interval '15 seconds') t
            ON CONFLICT (series_id, time) DO NOTHING""",  # noqa: S608
        [series.id],
    )
    after = sql("SELECT count(*) FROM metric_samples WHERE series_id = %s", [series.id])[0][0]
    assert after == before * 2
