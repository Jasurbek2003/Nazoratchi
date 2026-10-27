"""Zaxira tarixi (TZ 8.6, B10). Manba — agent yuboradigan `backup_*` metrikalari: yangi muvaffaqiyatli zaxira paydo
bo'lganda (`backup_last_success_timestamp` o'zgarganda) evaluator bitta `BackupRun` yozadi. Hajm anomaliyasi (AL-071/072)
va 30 kunlik hajm grafigi shu tarixdan hisoblanadi."""

from django.db import models
from django.utils import timezone

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
