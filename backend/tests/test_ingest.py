import gzip
import json
import time
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.metrics.models import Series, SeriesLatest
from apps.registry.models import AgentToken, Server

from .conftest import count_samples, make_batch, post_batch

pytestmark = pytest.mark.django_db


def sample(
    name: str = "cpu_busy_percent", value: float = 12.4, t_ms: int | None = None, **labels: str
) -> dict[str, Any]:
    return {
        "n": name,
        "t": t_ms if t_ms is not None else int(time.time() * 1000),
        "v": value,
        "l": labels,
    }


def test_valid_batch_is_stored(client: Client, agent: tuple[Server, str]) -> None:
    server, token = agent
    now = int(time.time() * 1000)
    batch = make_batch(
        [
            sample("cpu_busy_percent", 12.4, now),
            sample("fs_used_percent", 23.1, now, mount="/", device="/dev/sda1", fstype="ext4"),
        ]
    )
    response = post_batch(client, token, batch)
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] == 2 and data["rejected"] == 0 and data["duplicate"] is False
    assert count_samples() == 2
    assert SeriesLatest.objects.count() == 2
    server.refresh_from_db()
    assert server.status == "online" and server.last_seen_at is not None
    cpu = Series.objects.get(name="cpu_busy_percent")
    assert cpu.rollup is True and cpu.unit == "%"


def test_duplicate_batch_is_idempotent(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    batch = make_batch([sample(t_ms=int(time.time() * 1000))])
    assert post_batch(client, token, batch).json()["duplicate"] is False
    again = post_batch(client, token, batch).json()
    assert again["duplicate"] is True
    assert count_samples() == 1


def test_same_series_time_twice_in_one_batch(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    t = int(time.time() * 1000)
    post_batch(client, token, make_batch([sample(value=1.0, t_ms=t), sample(value=2.0, t_ms=t)]))
    assert count_samples() == 1


@pytest.mark.parametrize("token", [None, "agt_noto'g'ri"])
def test_missing_or_wrong_token_is_401(
    client: Client, agent: tuple[Server, str], token: str | None
) -> None:
    assert post_batch(client, token, make_batch([sample()])).status_code == 401


def test_revoked_token_is_401(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    AgentToken.objects.update(revoked_at=timezone.now())
    response = post_batch(client, token, make_batch([sample()]))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_revoked"


def test_get_is_405(client: Client) -> None:
    assert client.get("/ingest/v1/metrics").status_code == 405


def test_oversized_body_is_413(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    big = b"x" * (1_048_576 + 10)
    assert post_batch(client, token, big, compress=False).status_code == 413


def test_gzip_bomb_is_413(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    bomb = gzip.compress(b"\0" * 20_000_000)
    assert len(bomb) < 1_048_576
    assert post_batch(client, token, bomb, compress=True).status_code == 413


def test_corrupt_gzip_is_400(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    assert post_batch(client, token, b"bu gzip emas", compress=True).status_code == 400


def test_invalid_json_is_400(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    assert post_batch(client, token, b"{buzuq", compress=False).status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"seq": 1, "sent_at": "2026-10-26T10:00:00Z", "samples": []},
        {"batch_id": "b", "seq": -1, "sent_at": "2026-10-26T10:00:00Z"},
        {"batch_id": "b", "seq": 1, "sent_at": "2026-10-26T10:00:00Z", "samples": "x"},
    ],
)
def test_schema_errors_are_400(client: Client, agent: tuple[Server, str], payload: object) -> None:
    _, token = agent
    response = post_batch(client, token, payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_bad_samples_are_rejected_not_the_batch(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    now = int(time.time() * 1000)
    batch = make_batch(
        [
            sample("cpu_busy_percent", 140.0, now),  # diapazondan tashqari
            {"n": "mem_used_percent", "t": now, "v": float("nan")},  # NaN
            {"n": "mem_used_percent", "t": now, "v": float("inf")},  # Inf
            sample("load1", 0.5, now, url="https://x"),  # taqiqlangan belgi
            sample("Noto'g'ri-Nom", 1.0, now),
            {"n": "load1", "t": now, "v": "5"},  # son emas
            sample("load5", 0.4, now),  # yagona yaroqli
        ]
    )
    data = post_batch(client, token, batch).json()
    assert data["accepted"] == 1 and data["rejected"] == 6
    assert count_samples() == 1


def test_skewed_agent_clock_shifts_whole_batch(client: Client, agent: tuple[Server, str]) -> None:
    """Agent soati 11 daqiqa orqada: sent_at va namuna vaqtlari birga tuzatiladi (TZ 6.10)."""
    _, token = agent
    agent_now = timezone.now() - timedelta(minutes=11)
    t_ms = int(agent_now.timestamp() * 1000)
    batch = make_batch([sample(t_ms=t_ms)], sent_at=agent_now)
    data = post_batch(client, token, batch).json()
    assert data["clock_skew"] is True and data["accepted"] == 1
    assert abs(SeriesLatest.objects.get().time - timezone.now()) < timedelta(seconds=30)


def test_late_delivery_keeps_sample_time(client: Client, agent: tuple[Server, str]) -> None:
    """Core 14 daqiqa o'chib qaytdi: bufer namunasi o'z vaqti bilan yoziladi (FR-AGT-007)."""
    _, token = agent
    old = timezone.now() - timedelta(minutes=14)
    batch = make_batch([sample(t_ms=int(old.timestamp() * 1000))])
    data = post_batch(client, token, batch).json()
    assert data["clock_skew"] is False and data["accepted"] == 1
    assert abs(SeriesLatest.objects.get().time - old) < timedelta(seconds=1)


def test_too_old_and_future_samples_are_rejected(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    now = timezone.now()
    batch = make_batch(
        [
            sample(t_ms=int((now - timedelta(hours=2)).timestamp() * 1000)),
            sample("load1", 1.0, int((now + timedelta(minutes=5)).timestamp() * 1000)),
        ]
    )
    data = post_batch(client, token, batch).json()
    assert data["accepted"] == 0 and data["rejected"] == 2
    assert count_samples() == 0


@pytest.mark.parametrize("sent_at", [None, "ertaga", 123])
def test_sent_at_is_required(client: Client, agent: tuple[Server, str], sent_at: object) -> None:
    _, token = agent
    payload = {"batch_id": "b", "seq": 1, "samples": []}
    if sent_at is not None:
        payload["sent_at"] = sent_at
    assert post_batch(client, token, payload).status_code == 400


def test_cardinality_limit(
    client: Client, agent: tuple[Server, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, token = agent
    monkeypatch.setattr("apps.ingest.services.MAX_SERIES_PER_HOST", 3)
    now = int(time.time() * 1000)
    batch = make_batch([sample("fs_used_percent", 10.0, now, mount=f"/m{i}") for i in range(5)])
    data = post_batch(client, token, batch).json()
    assert data["accepted"] == 3 and data["rejected"] == 2
    assert Series.objects.count() == 3


def test_older_batch_does_not_overwrite_latest(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    now = int(time.time() * 1000)
    post_batch(client, token, make_batch([sample(value=50.0, t_ms=now)], batch_id="b-new", seq=2))
    post_batch(
        client, token, make_batch([sample(value=10.0, t_ms=now - 15_000)], batch_id="b-old", seq=1)
    )
    assert SeriesLatest.objects.get().value == 50.0


def test_non_gzip_body_accepted(client: Client, agent: tuple[Server, str]) -> None:
    _, token = agent
    body = json.dumps(make_batch([sample()])).encode()
    assert post_batch(client, token, body, compress=False).status_code == 200


def test_token_is_stored_only_as_hash(agent: tuple[Server, str]) -> None:
    _, token = agent
    stored = bytes(AgentToken.objects.get().token_hash)
    assert token.encode() not in stored and len(stored) == 32


@pytest.mark.parametrize(
    ("name", "kind", "unit"),
    [
        ("oom_kill_total", "counter", ""),  # haqiqiy hisoblagich
        ("procs_total", "gauge", ""),  # `_total` bilan tugaydi, lekin joriy son
        ("threads_total", "gauge", ""),
        ("fs_inodes_total", "gauge", ""),
        ("disk_await_ms", "gauge", "ms"),
        ("disk_write_bytes_per_sec", "gauge", "bayt/s"),
    ],
)
def test_f2_metric_kind_and_unit(name: str, kind: str, unit: str) -> None:
    from apps.ingest.catalog import kind_for, unit_for

    assert kind_for(name) == kind
    assert unit_for(name) == unit
