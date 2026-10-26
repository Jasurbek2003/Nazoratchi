"""Kirish mantig'i (TZ 14.3.2): blok, vaqtni tenglashtirish, audit."""

from datetime import timedelta

from django.contrib.auth import authenticate
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record
from apps.core.net import client_ip

from .models import User

MAX_FAILURES = 5
BASE_LOCK_MINUTES = 15
MAX_LOCK_MINUTES = 24 * 60


class InvalidCredentials(Exception):
    pass


class AccountLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("account_locked")
        self.retry_after = retry_after


def lock_minutes(failed_logins: int) -> int:
    """5-xatoda 15 daqiqa, 10-xatoda 30, 15-xatoda 60 ... (har keyingi blok 2 baravar, maks. 24 soat)."""
    level = failed_logins // MAX_FAILURES
    return int(min(BASE_LOCK_MINUTES * 2 ** (level - 1), MAX_LOCK_MINUTES))


def _register_failure(user: User) -> None:
    user.failed_logins += 1
    if user.failed_logins % MAX_FAILURES == 0:
        user.locked_until = timezone.now() + timedelta(minutes=lock_minutes(user.failed_logins))
    user.save(update_fields=["failed_logins", "locked_until"])


def verify_login(request: HttpRequest, login: str, password: str) -> User:
    """Yaroqli foydalanuvchini qaytaradi yoki `InvalidCredentials` / `AccountLocked`.

    Mavjud bo'lmagan login uchun ham xesh hisoblanadi (Django `authenticate` shuni qiladi): javob
    vaqti loginning mavjudligini oshkor qilmaydi (T-U-SEC-07).
    """
    ip = client_ip(request)
    user = User.objects.filter(login=login).first()
    now = timezone.now()
    if user is not None and user.locked_until and user.locked_until > now:
        record("login_blocked", user=user, ip=ip, object_type="user", object_id=user.id)
        raise AccountLocked(int((user.locked_until - now).total_seconds()) + 1)

    authenticated = authenticate(request, login=login, password=password)
    if authenticated is None or not isinstance(authenticated, User):
        if user is not None:
            _register_failure(user)
            if user.locked_until and user.locked_until > timezone.now():
                record("account_locked", user=user, ip=ip, object_type="user", object_id=user.id)
        # Kiritilgan login jurnalga yoziladi (parol hech qachon).
        record("login_failed", user=user, ip=ip, after={"login": login[:64]})
        raise InvalidCredentials
    if authenticated.failed_logins or authenticated.locked_until:
        authenticated.failed_logins = 0
        authenticated.locked_until = None
        authenticated.save(update_fields=["failed_logins", "locked_until"])
    return authenticated
