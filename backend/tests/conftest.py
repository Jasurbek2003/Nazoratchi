import gzip
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from apps.registry.models import AgentToken, Server


@pytest.fixture
def agent(db: None) -> tuple[Server, str]:
    server = Server.objects.create(name="main-2")
    _, token = AgentToken.issue(server)
    return server, token


def make_batch(
    samples: list[dict[str, Any]],
    batch_id: str = "b-1",
    seq: int = 1,
    sent_at: datetime | None = None,
) -> dict[str, Any]:
    sent = (sent_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z")
    return {"batch_id": batch_id, "seq": seq, "sent_at": sent, "samples": samples}


def post_batch(
    client: Client,
    token: str | None,
    payload: object | bytes,
    *,
    compress: bool = True,
) -> Any:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers: dict[str, str] = {}
    if compress:
        body = gzip.compress(body) if not isinstance(payload, bytes) else body
        headers["Content-Encoding"] = "gzip"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/ingest/v1/metrics", data=body, content_type="application/json", headers=headers
    )


def count_samples(series_id: int | None = None) -> int:
    with connection.cursor() as cursor:
        if series_id is None:
            cursor.execute("SELECT count(*) FROM metric_samples")
        else:
            cursor.execute("SELECT count(*) FROM metric_samples WHERE series_id = %s", [series_id])
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture(autouse=True)
def _reset_process_state() -> None:
    """Testlar orasida jarayon holati (tezlik chegarasi hisoblagichi, series keshi) tozalanadi."""
    from django.core.cache import cache

    from apps.ingest.services import clear_series_cache

    cache.clear()
    clear_series_cache()
