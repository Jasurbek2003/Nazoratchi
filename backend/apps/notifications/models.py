"""Bildirishnoma kanallari va yuborilgan xabarlar tarixi (TZ 8.8, FR-NTF-001/004)."""

from typing import Any

from django.db import models
from django.utils import timezone

from apps.core.crypto import decrypt_json, encrypt_json
from apps.core.ids import uuid7

SEVERITIES = ("info", "warning", "high", "critical")  # o'sish tartibida
SEVERITY_RANK = {name: i for i, name in enumerate(SEVERITIES)}


class Channel(models.Model):
    class Type(models.TextChoices):
        TELEGRAM = "telegram"
        EMAIL = "email"  # F2
        WEBHOOK = "webhook"  # F3

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    type = models.CharField(max_length=10, choices=Type)
    name = models.CharField(max_length=80, unique=True)
    config_enc = models.BinaryField()  # shifrlangan JSON: bot_token, chat_id (TZ 14.6)
    min_severity = models.CharField(
        max_length=10, choices=[(s, s) for s in SEVERITIES], default="warning"
    )
    quiet_hours = models.JSONField(
        null=True, blank=True
    )  # F2 (FR-NTF-006): hozircha faqat saqlanadi
    is_default = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(type__in=["telegram", "email", "webhook"]),
                name="channel_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(min_severity__in=list(SEVERITIES)),
                name="channel_min_severity_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    @property
    def _aad(self) -> bytes:
        return str(self.id).encode()

    def set_config(self, config: dict[str, Any]) -> None:
        self.config_enc = encrypt_json(config, self._aad)

    def get_config(self) -> dict[str, Any]:
        value: dict[str, Any] = decrypt_json(self.config_enc, self._aad)
        return value


class Notification(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        SENT = "sent"
        FAILED = "failed"
        SUPPRESSED = "suppressed"  # sokin soatlar (F2)

    id = models.BigAutoField(primary_key=True)
    # incidents jadvali S3 da paydo bo'ladi; shu paytgacha FK emas (keyin migratsiya bilan bog'lanadi).
    incident_id = models.UUIDField(null=True, blank=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="notifications")
    event = models.CharField(max_length=20)  # opened, escalated, resolved, reminder, digest, test
    status = models.CharField(max_length=10, choices=Status, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=64, blank=True)  # Telegram message_id
    error = models.TextField(blank=True, default="")
    # Qayta urinish uchun: yuboriladigan xabar (maxfiy qiymatlarsiz) va keyingi urinish vaqti.
    payload = models.JSONField(default=dict)
    next_attempt_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["incident_id", "created_at"], name="notifications_idx"),
            models.Index(
                fields=["next_attempt_at"],
                condition=models.Q(status="queued"),
                name="notifications_due_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["queued", "sent", "failed", "suppressed"]),
                name="notification_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event} -> {self.channel_id} ({self.status})"
