import importlib
import json
import logging
from typing import NoReturn

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError, connection
from django.test import Client

from apps.core.logging import JsonFormatter, mask_secrets


@pytest.mark.django_db
def test_healthz_ok(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_returns_503_when_db_down(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_cursor(*args: object, **kwargs: object) -> NoReturn:
        raise OperationalError("baza o'chiq")

    monkeypatch.setattr(connection, "cursor", broken_cursor)
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_healthz_rejects_post(client: Client) -> None:
    assert client.post("/healthz").status_code == 405


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer agt_abc123",
        "token=abc123",
        "PASSWORD: hunter2",
        "api_secret = xyz",
        '{"password": "hunter2"}',
        "authorization=Basic xyz",
    ],
)
def test_mask_secrets(text: str) -> None:
    masked = mask_secrets(text)
    assert "***" in masked
    for leaked in ("agt_abc123", "abc123", "hunter2", "xyz"):
        assert leaked not in masked


def test_json_formatter_masks_and_is_valid_json() -> None:
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "token=abc123 yuborildi", None, None
    )
    data = json.loads(JsonFormatter().format(record))
    assert data["level"] == "INFO"
    assert data["component"] == "test"
    assert "abc123" not in data["msg"]
    assert set(data) >= {"ts", "level", "component", "msg"}


def test_env_raises_when_required_variable_missing() -> None:
    from config.settings.base import env

    with pytest.raises(ImproperlyConfigured):
        env("NAZORATCHI_MAVJUD_EMAS_XYZ")


def test_prod_settings_are_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://nazoratchi.example.uz")
    prod = importlib.import_module("config.settings.prod")
    importlib.reload(prod)
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_HSTS_SECONDS >= 31_536_000
    assert prod.CSRF_TRUSTED_ORIGINS == ["https://nazoratchi.example.uz"]
