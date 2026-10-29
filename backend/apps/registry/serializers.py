from typing import Any

from rest_framework import serializers

from apps.core.dist import latest_agent_version, parse_version

from .models import Server


class ServerSerializer(serializers.ModelSerializer[Server]):
    # FR-AGT-011: panelda eskirgan agentlar belgilanadi. Tarqatish papkasidagi VERSION bilan solishtiriladi.
    agent_latest = serializers.SerializerMethodField()
    agent_outdated = serializers.SerializerMethodField()

    def _latest(self) -> str | None:
        # Ro'yxatda har server uchun faylni qayta o'qimaslik: bitta so'rov ichida bir marta.
        root = self.root  # many=True da ListSerializer: barcha elementlar uchun umumiy
        if not hasattr(root, "_agent_latest"):
            setattr(root, "_agent_latest", latest_agent_version())  # noqa: B010
        value: str | None = getattr(root, "_agent_latest")  # noqa: B009
        return value

    def get_agent_latest(self, obj: Server) -> str | None:
        return self._latest()

    def get_agent_outdated(self, obj: Server) -> bool | None:
        """True: agent eskirgan; False: eng yangi; None: versiya yoki reliz noma'lum (masalan, dev build)."""
        latest = self._latest()
        current = parse_version(obj.agent_version) if obj.agent_version else None
        target = parse_version(latest) if latest else None
        if current is None or target is None:
            return None
        return current < target

    class Meta:
        model = Server
        fields = [
            "id", "name", "provider", "public_ipv4", "public_ipv6", "role", "tags", "location",
            "monthly_cost_usd", "notes", "status", "last_seen_at", "paused_at", "paused_until",
            "pause_reason", "agent_version", "agent_update_to", "agent_latest", "agent_outdated", "facts",
            "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = [
            "id", "status", "last_seen_at", "paused_at", "paused_until", "pause_reason", "agent_version",
            "agent_update_to", "facts",
            "created_at", "updated_at",
        ]  # fmt: skip
        extra_kwargs: dict[str, Any] = {
            "name": {"validators": []}
        }  # noyoblik view'da tekshiriladi (409 duplicate)

    def validate_name(self, value: str) -> str:
        from .models import name_validator

        name_validator(value)
        return value
