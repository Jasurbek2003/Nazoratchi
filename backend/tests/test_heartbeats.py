"""Kiruvchi heartbeat `/hb/<token>` (FR-INT-005, TZ 9.14)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from apps.heartbeats.models import HeartbeatJob
from apps.registry.models import Server, hash_token

pytestmark = pytest.mark.django_db


@pytest.fixture
def job() -> tuple[HeartbeatJob, str]:
    return HeartbeatJob.issue("appctl-backup@main-2", 86400, grace_s=7200)


def test_ok_heartbeat_updates_job(client: Client, job: tuple[HeartbeatJob, str]) -> None:
    row, token = job
    response = client.get(f"/hb/{token}?status=ok&duration=42")
    assert response.status_code == 200 and response.content == b"ok\n"
    row.refresh_from_db()
    assert row.last_ok is True and row.last_duration_s == 42 and row.last_beat_at is not None
    assert row.last_message == ""


def test_fail_heartbeat_keeps_message(client: Client, job: tuple[HeartbeatJob, str]) -> None:
    row, token = job
    client.post(f"/hb/{token}?status=fail&msg=fail:%20Alpha,offsite")
    row.refresh_from_db()
    assert row.last_ok is False and row.last_message == "fail: Alpha,offsite"


def test_default_status_is_ok_and_message_is_truncated(
    client: Client, job: tuple[HeartbeatJob, str]
) -> None:
    row, token = job
    client.get(f"/hb/{token}?msg={'x' * 500}&duration=abc")
    row.refresh_from_db()
    assert row.last_ok is True and len(row.last_message) == 200 and row.last_duration_s is None


def test_invalid_status_is_400(client: Client, job: tuple[HeartbeatJob, str]) -> None:
    _, token = job
    assert client.get(f"/hb/{token}?status=yaxshi").status_code == 400


@pytest.mark.parametrize(
    "token", ["hb_yoq-token-12345", "x", "agt_boshqa-turdagi-token", "hb_" + "a" * 100]
)
def test_unknown_token_is_404(client: Client, token: str) -> None:
    assert client.get(f"/hb/{token}").status_code == 404


def test_disabled_job_is_404(client: Client, job: tuple[HeartbeatJob, str]) -> None:
    row, token = job
    row.enabled = False
    row.save()
    assert client.get(f"/hb/{token}").status_code == 404


def test_only_get_and_post_allowed(client: Client, job: tuple[HeartbeatJob, str]) -> None:
    _, token = job
    assert client.delete(f"/hb/{token}").status_code == 405


def test_rate_limit_10_per_minute_per_token(client: Client, job: tuple[HeartbeatJob, str]) -> None:
    _, token = job
    codes = [client.get(f"/hb/{token}").status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    assert "Retry-After" in client.get(f"/hb/{token}")


def test_token_is_stored_only_as_hash(job: tuple[HeartbeatJob, str]) -> None:
    row, token = job
    assert bytes(row.token_hash) == hash_token(token) and token.encode() not in bytes(
        row.token_hash
    )


def test_create_heartbeat_job_command_prints_path_once() -> None:
    Server.objects.create(name="main-2")
    out = StringIO()
    call_command(
        "create_heartbeat_job",
        "certbot-renew@main-2",
        "--every",
        "86400",
        "--server",
        "main-2",
        stdout=out,
    )
    text = out.getvalue()
    job = HeartbeatJob.objects.get(name="certbot-renew@main-2")
    assert job.server is not None and job.grace_s == 7200
    token = text.split("/hb/")[1].strip()
    assert bytes(job.token_hash) == hash_token(token)
