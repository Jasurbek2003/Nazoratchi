"""Reyestr (TZ 8.3): server va agent tokenlari. Prototipda faqat ingest uchun kerakli qism."""

import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone


class Server(models.Model):
    class Status(models.TextChoices):
        NEW = "new"
        ONLINE = "online"
        OFFLINE = "offline"
        PAUSED = "paused"
        ARCHIVED = "archived"

    # TZ 8.1: uuid v7. Python 3.13 da yo'q; prototipda uuid4, B1 da almashtiriladi.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.NEW)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    agent_version = models.CharField(max_length=40, blank=True)
    facts = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.name


def hash_token(token: str) -> bytes:
    """Tokenlar bazada faqat SHA-256 xesh sifatida saqlanadi (NFR-SEC-003)."""
    return hashlib.sha256(token.encode()).digest()


class AgentToken(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="tokens")
    name = models.CharField(max_length=60, default="agent")
    token_hash = models.BinaryField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.server.name}/{self.name}"

    @classmethod
    def issue(cls, server: Server, name: str = "agent") -> tuple["AgentToken", str]:
        """Yangi token yaratadi. Ochiq qiymat faqat shu yerda qaytadi, bazada saqlanmaydi."""
        token = "agt_" + secrets.token_urlsafe(32)  # 256 bit
        return cls.objects.create(server=server, name=name, token_hash=hash_token(token)), token
