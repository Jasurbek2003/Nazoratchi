"""Zaxira tarixi (TZ 8.6, B10). Manba — agent yuboradigan `backup_*` metrikalari: yangi muvaffaqiyatli zaxira paydo
bo'lganda (`backup_last_success_timestamp` o'zgarganda) evaluator bitta `BackupRun` yozadi. Hajm anomaliyasi (AL-071/072)
va 30 kunlik hajm grafigi shu tarixdan hisoblanadi."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.ids import uuid7
from apps.registry.models import Server


class BackupRun(models.Model):
    class Kind(models.TextChoices):
        DAILY = "daily"
        WEEKLY = "weekly"
        FILES = "files"

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="+")
    project_slug = models.CharField(max_length=60)
    kind = models.CharField(max_length=6, choices=Kind, default=Kind.DAILY)
    finished_at = models.DateTimeField()
    size_bytes = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["server", "project_slug", "kind", "finished_at"], name="backup_run_uq"
            )
        ]
        indexes = [models.Index(fields=["project_slug", "-finished_at"], name="backup_runs_idx")]

    def __str__(self) -> str:
        return f"{self.project_slug}@{self.server_id} {self.kind} {self.finished_at:%Y-%m-%d %H:%M}"


class SelfBackup(models.Model):
    """Nazoratchi o'z zaxirasini yuborish urinishlari (FR-SYS-003): muvaffaqiyat ham, xato ham. Yuborilmasa alert."""

    class Status(models.TextChoices):
        OK = "ok"
        FAILED = "failed"

    created_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=6, choices=Status)
    size_bytes = models.BigIntegerField(default=0)  # shifrlangan jami hajm
    parts = models.PositiveSmallIntegerField(default=0)
    channel_name = models.CharField(max_length=80, blank=True, default="")
    error = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["-created_at"], name="self_backups_idx")]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.status}"


class RestoreDrill(models.Model):
    """Restore drill (tiklash testi) natijasi, qo'lda kiritiladi (TZ 8.6, 10.8; FR-BKP-016, UC-11)."""

    class Result(models.TextChoices):
        SUCCESS = "success"
        PARTIAL = "partial"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey("registry.Project", on_delete=models.PROTECT, related_name="drills")
    performed_at = models.DateTimeField()
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    backup_file = models.CharField(max_length=300)
    backup_age_h = models.PositiveIntegerField(null=True, blank=True)
    duration_s = models.PositiveIntegerField(null=True, blank=True)  # RTO bahosi
    tables_count = models.PositiveIntegerField(null=True, blank=True)
    rows_count = models.PositiveBigIntegerField(null=True, blank=True)
    result = models.CharField(max_length=7, choices=Result)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "restore_drills"
        indexes = [models.Index(fields=["project", "-performed_at"], name="restore_drills_idx")]

    def __str__(self) -> str:
        return f"{self.project_id} {self.performed_at:%Y-%m-%d} {self.result}"
