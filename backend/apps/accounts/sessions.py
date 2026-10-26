"""Sessiya saqlagichi: Django DB sessiyasi + egasi (`user_id`). `SESSION_ENGINE = "apps.accounts.sessions"`."""

import uuid
from datetime import datetime
from typing import Any

from django.contrib.sessions.backends.db import SessionStore as DBSessionStore


class SessionStore(DBSessionStore):
    @classmethod
    def get_model_class(cls) -> Any:
        from .models import UserSession

        return UserSession

    def create_model_instance(self, data: dict[str, Any]) -> Any:
        """Django har saqlashda qatorni TO'LIQ qayta yozadi, shuning uchun egasi, ochiq id, IP va User-Agent
        sessiya ma'lumotining o'zida (`_pid`, `_ip`, `_ua`, `_created`) saqlanadi va shu yerdan ko'chiriladi."""
        instance: Any = super().create_model_instance(data)
        owner = data.get("_auth_user_id")
        instance.user_id = owner if owner else None
        if data.get("_pid"):
            instance.public_id = uuid.UUID(data["_pid"])
        instance.ip = data.get("_ip")
        instance.user_agent = data.get("_ua", "")
        if data.get("_created"):
            instance.created_at = datetime.fromisoformat(data["_created"])
        return instance
