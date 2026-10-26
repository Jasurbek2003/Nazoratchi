"""Foydalanuvchilar va sessiyalar (TZ 8.8, 14.3)."""

import uuid
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.sessions.base_session import AbstractBaseSession
from django.db import models
from django.utils import timezone as dj_timezone

from apps.core.ids import uuid7


class UserManager(BaseUserManager["User"]):
    def create_user(self, login: str, password: str, **extra: Any) -> "User":
        user = self.model(login=login, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    class Role(models.TextChoices):
        OWNER = "owner"
        OPERATOR = "operator"
        VIEWER = "viewer"

    class Language(models.TextChoices):
        UZ = "uz"
        RU = "ru"
        EN = "en"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    login = models.CharField(max_length=64, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    # `password` maydoni (AbstractBaseUser) argon2id xeshini saqlaydi (TZ: password_hash).
    role = models.CharField(max_length=10, choices=Role)
    totp_secret_enc = models.BinaryField(null=True, blank=True)  # F2 (2FA)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    language = models.CharField(max_length=2, choices=Language, default=Language.UZ)
    timezone = models.CharField(max_length=64, default="Asia/Tashkent")
    is_active = models.BooleanField(default=True)
    failed_logins = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now)

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["owner", "operator", "viewer"]), name="user_role_valid"
            )
        ]

    def __str__(self) -> str:
        return f"{self.login} ({self.role})"


class UserSession(AbstractBaseSession):
    """Server tomonidagi sessiya + ro'yxat va "hammasidan chiqish" uchun egasi (FR-AUTH-004)."""

    user_id = models.UUIDField(null=True, blank=True, db_index=True)
    # session_key emas. `unique` emas: Django `cycle_key()` yangi qatorni eskisi o'chirilishidan OLDIN yaratadi,
    # unique bo'lsa `create()` cheksiz qayta urinadi (P-02 emas, S1 da topilgan).
    public_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now)

    @classmethod
    def get_session_store_class(cls) -> Any:
        from .sessions import SessionStore

        return SessionStore
