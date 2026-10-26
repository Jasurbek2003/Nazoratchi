"""Audit jurnali (TZ 8.8, FR-AUD-001/002). Faqat qo'shiladi: UPDATE/DELETE ni DB triggeri taqiqlaydi."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    time = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=60)  # 'login', 'login_failed', 'server.create', ...
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"

    def __str__(self) -> str:
        return f"{self.time:%Y-%m-%d %H:%M:%S} {self.action}"
