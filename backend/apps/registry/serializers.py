from typing import Any

from rest_framework import serializers

from .models import Server


class ServerSerializer(serializers.ModelSerializer[Server]):
    class Meta:
        model = Server
        fields = [
            "id", "name", "provider", "public_ipv4", "public_ipv6", "role", "tags", "location",
            "monthly_cost_usd", "notes", "status", "last_seen_at", "paused_at", "paused_until",
            "pause_reason", "agent_version", "facts", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = [
            "id", "status", "last_seen_at", "paused_at", "paused_until", "pause_reason", "agent_version", "facts",
            "created_at", "updated_at",
        ]  # fmt: skip
        extra_kwargs: dict[str, Any] = {
            "name": {"validators": []}
        }  # noyoblik view'da tekshiriladi (409 duplicate)

    def validate_name(self, value: str) -> str:
        from .models import name_validator

        name_validator(value)
        return value
