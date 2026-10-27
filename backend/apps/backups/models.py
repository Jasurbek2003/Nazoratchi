"""Zaxira tarixi (TZ 8.6, B10). Manba — agent yuboradigan `backup_*` metrikalari: yangi muvaffaqiyatli zaxira paydo
bo'lganda (`backup_last_success_timestamp` o'zgarganda) evaluator bitta `BackupRun` yozadi. Hajm anomaliyasi (AL-071/072)
va 30 kunlik hajm grafigi shu tarixdan hisoblanadi."""

from django.db import models

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
