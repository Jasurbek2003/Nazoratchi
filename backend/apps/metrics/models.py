"""Vaqt qatorlari (TZ 8.4). `metric_samples` gipertablitsasi ORM modeli emas: u migratsiyada
SQL bilan yaratiladi va `apps.ingest.services` orqali xom SQL bilan yoziladi (COPY/unnest)."""

from django.db import models
from django.utils import timezone

from apps.registry.models import Server


class Series(models.Model):
    class Kind(models.TextChoices):
        GAUGE = "gauge"
        COUNTER = "counter"

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="series")
    name = models.CharField(max_length=100)
    labels = models.JSONField(default=dict, blank=True)
    labels_hash = models.CharField(max_length=32)
    unit = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=10, choices=Kind, default=Kind.GAUGE)
    # Agregat darajalarda saqlansinmi (muhim metrika). TZ 8.4.2 / R-102.
    rollup = models.BooleanField(default=False)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["server", "name", "labels_hash"], name="series_server_name_labels_uq"
            )
        ]
        indexes = [models.Index(fields=["server", "name"], name="series_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.name}{self.labels or ''}"


class SeriesLatest(models.Model):
    """Eng oxirgi qiymat (tez so'rovlar va alert uchun)."""

    series = models.OneToOneField(Series, on_delete=models.CASCADE, primary_key=True)
    time = models.DateTimeField()
    value = models.FloatField()

    def __str__(self) -> str:
        return f"{self.series_id}: {self.value} @ {self.time:%Y-%m-%d %H:%M:%S}"
