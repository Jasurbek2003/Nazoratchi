"""Kiruvchi heartbeat (FR-INT-005, TZ 8.6/9.14): cron va skriptlar "bajarildim" deb xabar beradi."""

import secrets
from typing import Any

from django.db import models

from apps.core.ids import uuid7
from apps.registry.models import Project, Server, hash_token


class HeartbeatJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=80, unique=True)  # 'appctl-backup@main-2'
    server = models.ForeignKey(
        Server, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    token_hash = models.BinaryField(unique=True)
    expected_every_s = models.PositiveIntegerField()
    grace_s = models.PositiveIntegerField(default=3600)
    last_beat_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(null=True, blank=True)
    last_message = models.CharField(max_length=200, blank=True)
    last_duration_s = models.PositiveIntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def issue(cls, name: str, expected_every_s: int, **extra: Any) -> tuple["HeartbeatJob", str]:
        token = "hb_" + secrets.token_urlsafe(24)
        return cls.objects.create(
            name=name, token_hash=hash_token(token), expected_every_s=expected_every_s, **extra
        ), token
