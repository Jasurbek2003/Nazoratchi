"""Chaos va nosozlik testlari (B13, TZ 16.6): fuzz oqim, kesh yo'qolishi, yagona leader."""

import gzip
import json
import random
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client

from apps.core.leader import Leader
from apps.registry.models import Server

from .conftest import make_batch, post_batch

pytestmark = pytest.mark.django_db


def test_fuzzed_bodies_never_cause_server_error(agent: tuple[Server, str]) -> None:
    """T-C-17: buzuq paket oqimi -> 4xx, hech qachon 5xx."""
    _, token = agent
    c = Client()
    rng = random.Random(1717)  # noqa: S311 - takrorlanuvchan fuzz, kriptografiya emas
    bodies: list[bytes] = [
        b"",
        b"null",
        b"[]",
        b"{" * 5000,
        b'{"a":' * 2000,
        b'{"samples": 1e999999}',
        b'{"batch_id": "' + b"x" * 100_000 + b'"}',
        json.dumps(make_batch([{"name": "cpu", "value": float("nan")}])).encode(),
        json.dumps(make_batch([{"name": "x" * 5000, "value": 1, "ts": "bad"}])).encode(),
        json.dumps(make_batch([{"name": None, "value": [1], "labels": "z"}])).encode(),
        "\ud800".encode("utf-8", "surrogatepass"),
        b"\xff\xfe\x00\x01",
    ]
    bodies += [rng.randbytes(rng.randint(1, 4000)) for _ in range(60)]
    for body in bodies:
        for compress in (False, True):
            raw = gzip.compress(body) if compress else body
            r = (
                post_batch(c, token, raw, compress=False)
                if not compress
                else c.post(
                    "/ingest/v1/metrics",
                    data=raw,
                    content_type="application/json",
                    headers={"Authorization": f"Bearer {token}", "Content-Encoding": "gzip"},
                )
            )
            # Yaroqsiz namuna namuna darajasida rad etiladi, paket 200 bo'lishi mumkin; 5xx esa hech qachon.
            assert r.status_code < 500, (body[:40], compress, r.status_code)
            assert r.headers["Content-Type"].startswith("application/json")


def test_fuzzed_auth_headers_are_401(agent: tuple[Server, str]) -> None:
    c = Client()
    for header in ("", "Bearer", "Bearer ", "Basic abc", "bearer \x00", "Bearer " + "A" * 10_000):
        r = c.post(
            "/ingest/v1/metrics",
            data=b"{}",
            content_type="application/json",
            headers={"Authorization": header} if header else {},
        )
        assert r.status_code == 401, header[:20]


def test_ingest_survives_cache_outage(
    agent: tuple[Server, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-C-02: redis (kesh) yo'q -> ingest ishlaydi (tezlik chegarasi fail-open)."""

    def boom(*a: Any, **k: Any) -> None:
        raise ConnectionError("redis o'chgan")

    monkeypatch.setattr(cache, "add", boom)
    monkeypatch.setattr(cache, "incr", boom)
    _, token = agent
    r = post_batch(Client(), token, make_batch([]))
    assert r.status_code == 200


def test_only_one_leader_at_a_time() -> None:
    """T-C-14: ikkita nusxadan faqat bittasi leader; birinchi chiqsa ikkinchisi egallaydi."""
    first, second = Leader("evaluator"), Leader("evaluator")
    try:
        assert first.ensure() is True
        assert second.ensure() is False
        assert first.ensure() is True  # leader o'zini qayta tasdiqlaydi
        first.release()
        assert second.ensure() is True
    finally:
        first.release()
        second.release()


def test_different_roles_do_not_block_each_other() -> None:
    a, b = Leader("evaluator"), Leader("prober")
    try:
        assert a.ensure() and b.ensure()
    finally:
        a.release()
        b.release()
