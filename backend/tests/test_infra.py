"""Yordamchi qatlam: uuid7, IP, tezlik chegarasi, fail-open kesh, series keshi, xato formati."""

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings

from apps.core import ratelimit
from apps.core.ids import uuid7
from apps.core.net import client_ip
from apps.ingest import services
from apps.metrics.models import Series
from apps.registry.models import Server

from .conftest import count_samples


# ---------------------------------------------------------------- uuid7
def test_uuid7_version_variant_and_time_ordering() -> None:
    first = uuid7()
    time.sleep(0.003)
    second = uuid7()
    assert first.version == 7 and first.variant == uuid.RFC_4122
    assert first < second  # vaqt bo'yicha tartiblangan
    assert len({uuid7() for _ in range(1000)}) == 1000
    embedded_ms = int.from_bytes(second.bytes[:6], "big")
    assert abs(embedded_ms - datetime.now(UTC).timestamp() * 1000) < 5000


# ---------------------------------------------------------------- client_ip
def request_with(**meta: str) -> Any:
    request = RequestFactory().get("/")
    request.META.update(meta)
    return request


def test_client_ip_ignores_forwarded_header_unless_trusted() -> None:
    request = request_with(REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert client_ip(request) == "10.0.0.5"
    with override_settings(TRUST_PROXY_HEADERS=True):
        assert client_ip(request) == "1.2.3.4"


def test_client_ip_takes_rightmost_forwarded_entry() -> None:
    """Mijoz soxta `X-Forwarded-For` yuborsa ham nginx qo'shgan OXIRGI qiymat olinadi."""
    request = request_with(REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 9.9.9.9")
    with override_settings(TRUST_PROXY_HEADERS=True):
        assert client_ip(request) == "9.9.9.9"


# ---------------------------------------------------------------- tezlik chegarasi
def test_ratelimit_allows_up_to_limit_then_blocks_with_retry_after() -> None:
    decisions = [ratelimit.hit("t", "a", limit=3, window_s=60) for _ in range(5)]
    assert [d.allowed for d in decisions] == [True, True, True, False, False]
    assert 0 < decisions[3].retry_after <= 60


def test_ratelimit_scopes_and_identities_are_independent() -> None:
    for _ in range(3):
        ratelimit.hit("t", "a", limit=3, window_s=60)
    assert not ratelimit.hit("t", "a", limit=3, window_s=60).allowed
    assert ratelimit.hit("t", "b", limit=3, window_s=60).allowed
    assert ratelimit.hit("boshqa", "a", limit=3, window_s=60).allowed


def test_ratelimit_fails_open_when_cache_breaks(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: object, **kwargs: object) -> Any:
        raise ConnectionError("redis yo'q")

    monkeypatch.setattr(cache, "add", broken)
    with caplog.at_level(logging.WARNING):
        assert ratelimit.hit("t", "a", limit=1, window_s=60).allowed
    assert "kesh xatosi" in caplog.text


def test_failopen_redis_cache_returns_defaults_when_redis_is_down(
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis_down = {
        "default": {
            "BACKEND": "apps.core.cache.FailOpenRedisCache",
            "LOCATION": "redis://127.0.0.1:9/0",  # port yopiq
            "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
        }
    }
    with override_settings(CACHES=redis_down), caplog.at_level(logging.WARNING):
        assert cache.get("k", "standart") == "standart"
        assert cache.add("k", 1, 10) is True  # "qo'shildi" deb hisoblanadi: so'rov o'tkaziladi
        assert cache.incr("k") == 0
        cache.set("k", 1, 10)
        assert cache.delete("k") is False
        assert ratelimit.hit("t", "x", limit=1, window_s=60).allowed
    assert "Redis mavjud emas" in caplog.text


# ---------------------------------------------------------------- xato formati
@pytest.mark.django_db
def test_api_errors_use_the_tz_format(client: Client) -> None:
    response = client.get("/api/v1/auth/me")
    body = response.json()["error"]
    assert response.status_code == 401
    assert set(body) >= {"code", "message", "request_id"} and body["request_id"].startswith("req_")
    assert client.get("/api/v1/yoq-yol").status_code == 404
    bad = client.post("/api/v1/auth/login", b"{", content_type="application/json")
    assert bad.status_code in (400, 403)


# ---------------------------------------------------------------- series keshi
@pytest.mark.django_db
def test_series_map_is_cached_between_batches(django_assert_num_queries: Any) -> None:
    server = Server.objects.create(name="kesh-test")
    Series.objects.create(server=server, name="load1", labels_hash="a", rollup=True)
    first = services._series_map(server)
    with django_assert_num_queries(0):
        assert services._series_map(server) is first


@pytest.mark.django_db
def test_series_cache_expires_and_can_be_bypassed() -> None:
    server = Server.objects.create(name="kesh-test")
    services._series_map(server)
    Series.objects.create(server=server, name="load1", labels_hash="a")
    assert services._series_map(server) == {}  # kesh yangilanmagan
    assert len(services._series_map(server, use_cache=False)) == 1
    services._series_cache[server.pk] = (time.monotonic() - services.SERIES_CACHE_TTL_S - 1, {})
    assert len(services._series_map(server)) == 1  # muddati o'tgach qayta o'qiladi


@pytest.mark.django_db(transaction=True)
def test_failed_batch_does_not_poison_series_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rollback bo'lgan yangi seriya idlari keshda qolmasligi kerak (aks holda ma'lumot "yo'q" seriyaga yoziladi)."""
    server = Server.objects.create(name="kesh-test")
    now_ms = int(time.time() * 1000)
    samples = [{"n": "load1", "t": now_ms, "v": 1.0, "l": {}}]

    def boom(rows: Any) -> int:
        raise RuntimeError("yozish xatosi")

    monkeypatch.setattr(services, "_write_samples", boom)
    with pytest.raises(RuntimeError):
        services.ingest_batch(server, samples, datetime.now(UTC))
    assert Series.objects.count() == 0  # tranzaksiya qaytdi
    assert server.pk not in services._series_cache or services._series_cache[server.pk][1] == {}
    monkeypatch.undo()
    result = services.ingest_batch(server, samples, datetime.now(UTC))
    assert result.accepted == 1 and Series.objects.count() == 1 and count_samples() == 1
