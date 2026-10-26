"""Autentifikatsiya, sessiyalar, RBAC (TZ 9.2, 14.3, 14.4; FR-AUTH-001/002/004/007)."""

from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import User, UserSession
from apps.accounts.services import lock_minutes
from apps.audit.models import AuditLog

PASSWORD = "Kuchli-parol-2026!"
pytestmark = pytest.mark.django_db


def make_user(login: str = "jasur", role: str = "owner", password: str = PASSWORD) -> User:
    return User.objects.create_user(login, password, role=role)


def csrf_client() -> Client:
    return Client(enforce_csrf_checks=True)


def login(client: Client, login_name: str = "jasur", password: str = PASSWORD) -> Any:
    """CSRF cookie olib, keyin kiradi (SPA oqimi)."""
    client.get("/api/v1/auth/csrf")
    token = client.cookies["csrftoken"].value
    return client.post(
        "/api/v1/auth/login",
        {"login": login_name, "password": password},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )


def csrf_headers(client: Client) -> dict[str, str]:
    return {"X-CSRFToken": client.cookies["csrftoken"].value}


def actions() -> list[str]:
    return list(AuditLog.objects.order_by("id").values_list("action", flat=True))


# ---------------------------------------------------------------- kirish / chiqish
def test_login_me_logout_flow() -> None:
    make_user()
    client = csrf_client()
    response = login(client)
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["login"] == "jasur" and user["role"] == "owner" and user["mfa_enabled"] is False
    assert user["language"] == "uz" and user["timezone"] == "Asia/Tashkent"
    cookie = client.cookies["nzr_sid"]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert client.get("/api/v1/auth/me").json()["login"] == "jasur"
    assert (
        client.post(
            "/api/v1/auth/logout", content_type="application/json", headers=csrf_headers(client)
        ).status_code
        == 204
    )
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["error"]["code"] == "unauthenticated"
    assert actions() == ["login", "logout"]


def test_login_without_csrf_token_is_rejected() -> None:
    make_user()
    response = csrf_client().post(
        "/api/v1/auth/login",
        {"login": "jasur", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403


def test_wrong_password_and_unknown_login_look_identical() -> None:
    make_user()
    a = login(csrf_client(), "jasur", "noto'g'ri-parol-123")
    b = login(csrf_client(), "yoq-odam", "noto'g'ri-parol-123")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"] == "unauthenticated"
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_unknown_login_still_hashes_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-U-SEC-07: mavjud bo'lmagan login uchun ham xesh hisoblanadi (vaqt orqali oshkor bo'lmasin)."""
    calls: list[str] = []
    original = User.set_password

    def counting(self: User, raw: str | None) -> None:
        calls.append("hash")
        original(self, raw)

    monkeypatch.setattr(User, "set_password", counting)
    login(csrf_client(), "yoq-odam", "xohlagan-parol-123")
    assert calls == ["hash"]


def test_account_locks_after_five_failures_and_unlocks_on_success_later() -> None:
    user = make_user()
    client = csrf_client()
    for _ in range(4):
        assert login(client, "jasur", "xato-parol-12345").status_code == 401
    assert login(client, "jasur", "xato-parol-12345").status_code == 401  # 5-xato: endi bloklangan
    locked = login(client, "jasur", PASSWORD)  # to'g'ri parol ham o'tmaydi
    assert locked.status_code == 423 and locked.json()["error"]["code"] == "account_locked"
    assert 800 < int(locked["Retry-After"]) <= 900  # ~15 daqiqa
    assert {"login_failed", "account_locked", "login_blocked"} <= set(actions())
    user.refresh_from_db()
    user.locked_until = timezone.now() - timedelta(seconds=1)  # blok muddati o'tdi
    user.save()
    assert login(client, "jasur", PASSWORD).status_code == 200
    user.refresh_from_db()
    assert user.failed_logins == 0 and user.locked_until is None


@pytest.mark.parametrize(
    ("failures", "minutes"),
    [(5, 15), (10, 30), (15, 60), (20, 120), (60, 1440), (100, 1440)],
)
def test_lock_duration_doubles_up_to_24_hours(failures: int, minutes: int) -> None:
    assert lock_minutes(failures) == minutes


def test_failed_login_audit_never_contains_the_password() -> None:
    make_user()
    login(csrf_client(), "jasur", "maxfiy-xato-parol-999")
    dump = str(list(AuditLog.objects.values()))
    assert "maxfiy-xato-parol-999" not in dump and "login_failed" in dump


def test_login_throttle_returns_429_in_error_format() -> None:
    client = csrf_client()
    statuses = [login(client, f"odam{i}", "xato-parol-12345").status_code for i in range(12)]
    assert statuses[:10] == [401] * 10
    response = login(client, "odam99", "xato-parol-12345")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited" and "Retry-After" in response


# ---------------------------------------------------------------- parol
def test_passwords_are_hashed_with_argon2id_and_tz_parameters() -> None:
    with override_settings(
        PASSWORD_HASHERS=["apps.accounts.hashers.NazoratchiArgon2PasswordHasher"]
    ):
        user = make_user("argon", password=PASSWORD)
        assert user.password.startswith("argon2$argon2id$v=19$m=65536,t=3,p=2$")
        assert user.check_password(PASSWORD)


@pytest.mark.parametrize("weak", ["qisqa-1", "password1234", "123456789012"])
def test_weak_passwords_are_rejected_on_change(weak: str) -> None:
    make_user()
    client = csrf_client()
    login(client)
    response = client.patch(
        "/api/v1/auth/me",
        {"current_password": PASSWORD, "new_password": weak},
        content_type="application/json",
        headers=csrf_headers(client),
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "new_password"


def test_password_change_invalidates_other_sessions() -> None:
    make_user()
    first, second = csrf_client(), csrf_client()
    login(first)
    login(second)
    response = first.patch(
        "/api/v1/auth/me",
        {"current_password": PASSWORD, "new_password": "Yangi-kuchli-parol-77"},
        content_type="application/json",
        headers=csrf_headers(first),
    )
    assert response.status_code == 200
    assert first.get("/api/v1/auth/me").status_code == 200  # joriy sessiya saqlanadi
    assert second.get("/api/v1/auth/me").status_code == 401  # boshqalari tugaydi
    assert login(csrf_client(), "jasur", "Yangi-kuchli-parol-77").status_code == 200
    assert "password_changed" in actions()
    assert "Yangi-kuchli" not in str(list(AuditLog.objects.values()))


def test_password_change_requires_correct_current_password() -> None:
    make_user()
    client = csrf_client()
    login(client)
    response = client.patch(
        "/api/v1/auth/me",
        {"current_password": "boshqa-parol-12345", "new_password": "Yangi-kuchli-parol-77"},
        content_type="application/json",
        headers=csrf_headers(client),
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "current_password"


def test_profile_update_validates_language_and_timezone() -> None:
    make_user()
    client = csrf_client()
    login(client)

    def patch(body: dict[str, str]) -> Any:
        return client.patch(
            "/api/v1/auth/me", body, content_type="application/json", headers=csrf_headers(client)
        )

    ok = patch({"language": "ru", "timezone": "Europe/Moscow"})
    assert ok.status_code == 200 and ok.json()["language"] == "ru"
    assert patch({"language": "klingon"}).status_code == 400
    assert patch({"timezone": "Mars/Olympus"}).status_code == 400
    assert (
        patch({"new_password": "Yangi-kuchli-parol-77"}).status_code == 400
    )  # current_password yo'q


# ---------------------------------------------------------------- sessiyalar
def test_sessions_list_revoke_and_logout_all() -> None:
    user = make_user()
    other = make_user("boshqa", "operator")
    first, second, stranger = csrf_client(), csrf_client(), csrf_client()
    login(first)
    login(second)
    login(stranger, "boshqa")
    items = first.get("/api/v1/auth/sessions").json()["items"]
    assert len(items) == 2 and sum(1 for i in items if i["current"]) == 1
    assert "session_key" not in str(items)  # sessiya kaliti hech qachon chiqmaydi
    their = next(i for i in items if not i["current"])
    assert (
        stranger.delete(
            f"/api/v1/auth/sessions/{their['id']}", headers=csrf_headers(stranger)
        ).status_code
        == 404
    )
    assert (
        first.delete(
            f"/api/v1/auth/sessions/{their['id']}", headers=csrf_headers(first)
        ).status_code
        == 204
    )
    assert second.get("/api/v1/auth/me").status_code == 401
    login(second)
    assert (
        first.post(
            "/api/v1/auth/logout-all", content_type="application/json", headers=csrf_headers(first)
        ).status_code
        == 204
    )
    assert (
        first.get("/api/v1/auth/me").status_code == 401
        and second.get("/api/v1/auth/me").status_code == 401
    )
    assert stranger.get("/api/v1/auth/me").status_code == 200  # boshqa foydalanuvchiga tegilmagan
    assert UserSession.objects.filter(user_id=user.id).count() == 0
    assert UserSession.objects.filter(user_id=other.id).count() == 1


def test_session_records_ip_and_user_agent() -> None:
    make_user()
    client = csrf_client()
    client.get("/api/v1/auth/csrf")
    client.post(
        "/api/v1/auth/login",
        {"login": "jasur", "password": PASSWORD},
        content_type="application/json",
        headers={
            "X-CSRFToken": client.cookies["csrftoken"].value,
            "User-Agent": "Mozilla/5.0 test",
        },
    )
    session = UserSession.objects.get()
    assert session.ip == "127.0.0.1" and session.user_agent == "Mozilla/5.0 test"


def test_session_expires_after_absolute_lifetime() -> None:
    make_user()
    client = csrf_client()
    login(client)
    session = client.session
    session["login_at"] = int((timezone.now() - timedelta(days=8)).timestamp())
    session.save()
    assert client.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------- RBAC
def test_undeclared_endpoints_are_denied_by_default() -> None:
    from django.urls import path
    from rest_framework.response import Response
    from rest_framework.views import APIView

    class Undeclared(APIView):
        def get(self, request: Any) -> Response:
            return Response({"gizli": True})

    urlconf = type("urlconf", (), {"urlpatterns": [path("x", Undeclared.as_view())]})
    with override_settings(ROOT_URLCONF=urlconf):
        response = Client().get("/x")
    assert response.status_code in (401, 403) and "gizli" not in response.content.decode()


def test_roles_matrix_for_server_creation() -> None:
    make_user("egasi", "owner")
    make_user("operator", "operator")
    make_user("kuzatuvchi", "viewer")
    expected = {"egasi": 201, "operator": 201, "kuzatuvchi": 403}
    for i, (name, status) in enumerate(expected.items()):
        client = csrf_client()
        login(client, name)
        response = client.post(
            "/api/v1/servers/",
            {"name": f"srv-{i}"},
            content_type="application/json",
            headers=csrf_headers(client),
        )
        assert response.status_code == status, name
    anonymous = Client().post("/api/v1/servers/", {"name": "x1"}, content_type="application/json")
    assert anonymous.status_code in (401, 403)


def test_authenticated_unsafe_requests_need_csrf_header() -> None:
    make_user()
    client = csrf_client()
    login(client)
    response = client.post("/api/v1/servers/", {"name": "srv-a"}, content_type="application/json")
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"


# ---------------------------------------------------------------- audit
def test_audit_log_is_append_only() -> None:
    make_user()
    login(csrf_client())
    entry = AuditLog.objects.first()
    assert entry is not None
    with pytest.raises(IntegrityError, match="faqat qo.shiladi"), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(action="soxta")
    with pytest.raises(IntegrityError, match="faqat qo.shiladi"), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()
    entry.refresh_from_db()
    assert entry.action == "login"


def test_audit_masks_secret_fields() -> None:
    from apps.audit.services import mask, record

    masked = mask(
        {
            "login": "x",
            "password": "a",
            "nested": {"api_key": "b", "agent_token": "c"},
            "items": [{"secret": "d"}],
        }
    )
    assert masked == {
        "login": "x",
        "password": "***",
        "nested": {"api_key": "***", "agent_token": "***"},
        "items": [{"secret": "***"}],
    }
    row = record("test", after={"token": "agt_abc", "ok": 1})
    assert row.after == {"token": "***", "ok": 1}
