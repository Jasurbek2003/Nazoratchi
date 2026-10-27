"""Faol tekshiruvlar (TZ 8.5): `probes` jadvali. Natijalar (`probe_results`) Timescale gipertablitsasi —
ORM modeli emas, xom SQL bilan yoziladi (migratsiyada yaratiladi)."""

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.core.ids import uuid7
from apps.registry.models import Domain, Project, Server


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


class CertStatus(models.Model):
    """Eng oxirgi sertifikat holati (TZ 8.5): TLS tekshiruvi (`probe`) yoki agent skaneri (`agent`, B5c)."""

    class Source(models.TextChoices):
        PROBE = "probe"
        AGENT = "agent"

    domain = models.ForeignKey(
        Domain, null=True, blank=True, on_delete=models.SET_NULL, related_name="certs"
    )
    server = models.ForeignKey(
        Server, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(max_length=253)
    source = models.CharField(max_length=5, choices=Source)
    not_after = models.DateTimeField()
    issuer = models.CharField(max_length=300, blank=True, default="")
    subject = models.CharField(max_length=300, blank=True, default="")
    san = ArrayField(models.CharField(max_length=253), default=list, blank=True)
    chain_ok = models.BooleanField(null=True, blank=True)
    hostname_ok = models.BooleanField(null=True, blank=True)
    checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "source", "server"], nulls_distinct=False, name="cert_status_uq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.source}) -> {self.not_after:%Y-%m-%d}"


class DnsChange(models.Model):
    """DNS javobi o'zgarish tarixi (FR-DNS-008): `A: 34.173.220.247 -> 164.68.105.194`."""

    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="dns_changes")
    resolver = models.CharField(max_length=80)
    rtype = models.CharField(max_length=10)
    old_answers = ArrayField(models.CharField(max_length=100), default=list)
    new_answers = ArrayField(models.CharField(max_length=100), default=list)
    changed_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.domain_id} {self.resolver}: {self.old_answers} -> {self.new_answers}"
