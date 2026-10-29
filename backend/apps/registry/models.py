"""Reyestr (TZ 8.3): serverlar, loyihalar, domenlar, tokenlar, host voqealari.

Eslatma: `project_servers` TZ da kompozit kalitli; ORM qulayligi uchun surrogate `id` + UNIQUE cheklov.
"""

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.ids import uuid7

ENROLL_TOKEN_TTL = timedelta(hours=1)

name_validator = RegexValidator(r"^[A-Za-z0-9_-]{2,40}$", "2–40 belgi: harf, raqam, '-' va '_'.")
slug_validator = RegexValidator(r"^[A-Za-z0-9_-]+$", "Faqat harf, raqam, '-' va '_'.")


def hash_token(token: str) -> bytes:
    """Tokenlar bazada faqat SHA-256 xesh sifatida saqlanadi (NFR-SEC-003)."""
    return hashlib.sha256(token.encode()).digest()


class Server(models.Model):
    class Status(models.TextChoices):
        NEW = "new"
        ONLINE = "online"
        OFFLINE = "offline"
        PAUSED = "paused"
        ARCHIVED = "archived"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=40, unique=True, validators=[name_validator])
    provider = models.CharField(max_length=80, blank=True)
    public_ipv4 = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    public_ipv6 = models.GenericIPAddressField(protocol="IPv6", null=True, blank=True)
    role = models.CharField(max_length=40, blank=True)
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    location = models.CharField(max_length=80, blank=True)
    monthly_cost_usd = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status, default=Status.NEW)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_until = models.DateTimeField(
        null=True, blank=True
    )  # muddati o'tgach avtomatik davom etadi
    pause_reason = models.CharField(max_length=200, blank=True, default="")
    paused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    agent_version = models.CharField(max_length=40, blank=True)
    # Owner so'ragan agent yangilanishi (FR-AGT-008): nishon versiya; host shu versiyaga yetgach tozalanadi.
    agent_update_to = models.CharField(max_length=40, blank=True, default="")
    facts = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class Project(models.Model):
    class Kind(models.TextChoices):
        COMPOSE = "compose"
        SYSTEMD = "systemd"
        STATIC = "static"
        OTHER = "other"

    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    slug = models.CharField(
        max_length=60, unique=True, validators=[slug_validator]
    )  # appctl papka nomi
    name = models.CharField(max_length=60)
    description = models.TextField(blank=True, default="")
    owner_name = models.CharField(max_length=80, blank=True)
    owner_contact = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=10, choices=Kind)
    moved = models.BooleanField(default=True)  # False = "ko'chirilmagan"
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    # Zaxira siyosati (seed `backup:`): expect_daily, expect_weekly_files, require_offsite, db. Bo'sh = kuzatilmaydi.
    backup = models.JSONField(default=dict, blank=True)
    links = models.JSONField(default=list, blank=True)  # [{label, url}]
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    servers = models.ManyToManyField(Server, through="ProjectServer", related_name="projects")

    def __str__(self) -> str:
        return self.slug


class ProjectServer(models.Model):
    class Environment(models.TextChoices):
        PRODUCTION = "production"
        STAGING = "staging"
        DEV = "dev"

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    environment = models.CharField(
        max_length=10, choices=Environment, default=Environment.PRODUCTION
    )
    ports = ArrayField(models.PositiveIntegerField(), default=list, blank=True)  # 127.0.0.1 portlar

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "server", "environment"], name="project_server_env_uq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.project_id}@{self.server_id} ({self.environment})"


class Domain(models.Model):
    class ControlledBy(models.TextChoices):
        SELF = "self"
        CLIENT = "client"
        OTHER = "other"

    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="domains"
    )
    fqdn = models.CharField(max_length=253, unique=True)
    expected_ips = ArrayField(models.GenericIPAddressField(), default=list, blank=True)
    dns_provider = models.CharField(max_length=80, blank=True)
    registrar = models.CharField(max_length=80, blank=True)
    controlled_by = models.CharField(max_length=10, choices=ControlledBy, default=ControlledBy.SELF)
    tls_enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(fqdn=Lower("fqdn")), name="domain_fqdn_lower")
        ]

    def __str__(self) -> str:
        return self.fqdn


class AgentToken(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="tokens")
    name = models.CharField(max_length=60, default="agent")
    token_hash = models.BinaryField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.server.name}/{self.name}"

    @classmethod
    def issue(
        cls, server: Server, name: str = "agent", created_by: Any = None
    ) -> tuple["AgentToken", str]:
        """Yangi token yaratadi. Ochiq qiymat faqat shu yerda qaytadi, bazada saqlanmaydi."""
        token = "agt_" + secrets.token_urlsafe(32)  # 256 bit
        row = cls.objects.create(
            server=server, name=name, token_hash=hash_token(token), created_by=created_by
        )
        return row, token


class EnrollToken(models.Model):
    """Bir martalik token (1 soat): agent birinchi ulanishda doimiy tokenga almashtiradi (FR-AGT-002)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    token_hash = models.BinaryField(unique=True)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="enroll_tokens")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return f"enroll:{self.server_id}"

    @classmethod
    def issue(cls, server: Server, created_by: Any = None) -> tuple["EnrollToken", str]:
        token = "enr_" + secrets.token_urlsafe(24)
        row = cls.objects.create(
            server=server,
            token_hash=hash_token(token),
            expires_at=timezone.now() + ENROLL_TOKEN_TTL,
            created_by=created_by,
        )
        return row, token


class HostEvent(models.Model):
    """Reboot, fakt o'zgarishi, agent yangilanishi, enroll, pauza va h.k."""

    id = models.BigAutoField(primary_key=True)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="events")
    time = models.DateTimeField(default=timezone.now)
    type = models.CharField(max_length=40)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["server", "-time"], name="host_events_idx")]

    def __str__(self) -> str:
        return f"{self.type}@{self.server_id}"


class Setting(models.Model):
    """Tizim darajasidagi kichik sozlamalar (masalan, `retired_ips` — o'chirilgan IP lar, Q-12)."""

    key = models.CharField(max_length=60, primary_key=True)
    value = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.key

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        row = cls.objects.filter(key=key).first()
        return row.value if row else default
