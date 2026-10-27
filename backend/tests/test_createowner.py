"""`createowner` boshqaruv buyrug'i (TZ 15.7)."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.audit.models import AuditLog

PASSWORD = "Kuchli-parol-2026!"
pytestmark = pytest.mark.django_db


def test_creates_owner_from_env_password_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAZORATCHI_OWNER_PASSWORD", PASSWORD)
    call_command("createowner", login="jasur")
    user = User.objects.get(login="jasur")
    assert user.role == User.Role.OWNER
    assert user.check_password(PASSWORD)
    entry = AuditLog.objects.get(action="user.create")
    assert entry.object_id == str(user.id)
    assert PASSWORD not in str(entry.after)


def test_prompts_and_requires_matching_passwords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NAZORATCHI_OWNER_PASSWORD", raising=False)
    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    with pytest.raises(CommandError, match="mos kelmadi"):
        call_command("createowner", login="jasur")
    assert not User.objects.exists()

    answers = iter([PASSWORD, PASSWORD])
    call_command("createowner", login="jasur")
    assert User.objects.filter(login="jasur").exists()


def test_rejects_weak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAZORATCHI_OWNER_PASSWORD", "123")
    with pytest.raises(CommandError, match="talablarga javob bermaydi"):
        call_command("createowner", login="jasur")
    assert not User.objects.exists()


def test_rejects_existing_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAZORATCHI_OWNER_PASSWORD", PASSWORD)
    call_command("createowner", login="jasur")
    with pytest.raises(CommandError, match="mavjud"):
        call_command("createowner", login="jasur")
    assert User.objects.count() == 1
