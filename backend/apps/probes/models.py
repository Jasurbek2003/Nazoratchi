"""Faol tekshiruvlar (TZ 8.5): `probes` jadvali. Natijalar (`probe_results`) Timescale gipertablitsasi —
ORM modeli emas, xom SQL bilan yoziladi (migratsiyada yaratiladi)."""

from django.db import models
from django.utils import timezone

from apps.core.ids import uuid7
from apps.registry.models import Domain, Project


class Probe(models.Model):
    class Type(models.TextChoices):
        HTTP = "http"
        TCP = "tcp"
        TLS = "tls"  # S5
        DNS = "dns"  # S5
        WHOIS = "whois"  # S5

    class State(models.TextChoices):
        UP = "up"
        DOWN = "down"
        UNKNOWN = "unknown"
        PAUSED = "paused"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="probes"
    )
    domain = models.ForeignKey(
        Domain, null=True, blank=True, on_delete=models.SET_NULL, related_name="probes"
    )
    type = models.CharField(max_length=5, choices=Type)
    name = models.CharField(max_length=120)
    config = models.JSONField()
    interval_s = models.PositiveIntegerField(default=60)
    timeout_s = models.PositiveSmallIntegerField(default=10)
    enabled = models.BooleanField(default=True)
    state = models.CharField(max_length=7, choices=State, default=State.UNKNOWN)
    state_since = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(default=timezone.now)
    secrets_enc = models.BinaryField(
        null=True, blank=True
    )  # shifrlangan sarlavhalar (keyingi sprint)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(interval_s__gte=10, interval_s__lte=86400),
                name="probe_interval_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(timeout_s__gte=1, timeout_s__lte=60), name="probe_timeout_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=["http", "tcp", "tls", "dns", "whois"]),
                name="probe_type_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_run_at"], condition=models.Q(enabled=True), name="probes_due_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.type}:{self.name}"
