import re
from typing import Any

from rest_framework import serializers

from apps.core.crypto import DecryptionError

from .models import SEVERITIES, Channel, Notification

_BOT_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")
_CHAT_USERNAME_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9_]{4,31}$")
MASK = "••••"


def _validate_telegram_config(config: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    """Faqat ma'lum kalitlar; `bot_token` shakli tekshiriladi (qisman yangilashda ixtiyoriy)."""
    unknown = set(config) - {"bot_token", "chat_id"}
    if unknown:
        raise serializers.ValidationError(f"Noma'lum kalitlar: {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    if "bot_token" in config or not partial:
        token = config.get("bot_token")
        if not isinstance(token, str) or not _BOT_TOKEN_RE.match(token):
            raise serializers.ValidationError(
                "bot_token noto'g'ri (BotFather formati: 123456:ABC...)."
            )
        out["bot_token"] = token
    if "chat_id" in config or not partial:
        chat = config.get("chat_id")
        if isinstance(chat, bool) or not (
            isinstance(chat, int) or (isinstance(chat, str) and _CHAT_USERNAME_RE.match(chat))
        ):
            raise serializers.ValidationError(
                "chat_id butun son (shaxsiy/guruh) yoki @kanal_nomi bo'lishi kerak."
            )
        out["chat_id"] = chat
    return out


class ChannelSerializer(serializers.ModelSerializer[Channel]):
    # Yozishda `config` (sirlar bilan); o'qishda hech qachon qaytarilmaydi, o'rniga `config_masked`.
    config = serializers.JSONField(write_only=True, required=False)
    config_masked = serializers.SerializerMethodField()

    class Meta:
        model = Channel
        fields = [
            "id", "type", "name", "min_severity", "quiet_hours", "is_default", "enabled",
            "last_ok_at", "last_error", "config", "config_masked",
        ]  # fmt: skip
        read_only_fields = ["id", "last_ok_at", "last_error"]
        extra_kwargs: dict[str, Any] = {"name": {"validators": []}}  # noyoblik view'da (409)

    def validate_type(self, value: str) -> str:
        if value != Channel.Type.TELEGRAM:
            raise serializers.ValidationError(
                "Hozircha faqat telegram kanali qo'llab-quvvatlanadi (email F2, webhook F3)."
            )
        return value

    def validate_min_severity(self, value: str) -> str:
        if value not in SEVERITIES:
            raise serializers.ValidationError(f"{', '.join(SEVERITIES)} dan biri bo'lishi kerak.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        creating = self.instance is None
        if creating and "config" not in attrs:
            raise serializers.ValidationError({"config": "Majburiy."})
        if "type" in attrs and not creating and attrs["type"] != self.instance.type:  # type: ignore[union-attr]
            raise serializers.ValidationError({"type": "Kanal turini o'zgartirib bo'lmaydi."})
        if "config" in attrs:
            if not isinstance(attrs["config"], dict):
                raise serializers.ValidationError({"config": "Obyekt bo'lishi kerak."})
            try:
                attrs["config"] = _validate_telegram_config(attrs["config"], partial=not creating)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"config": exc.detail}) from None
        return attrs

    def get_config_masked(self, obj: Channel) -> dict[str, Any]:
        """Sir yashiriladi (TZ 9.9: `bot_token: "••••"`); chat_id sir emas."""
        try:
            config = obj.get_config()
        except DecryptionError:
            return {"error": "shifrni ochib bo'lmadi (kalit almashtirilgan?)"}
        return {"bot_token": MASK, "chat_id": config.get("chat_id")}


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    channel_name = serializers.CharField(source="channel.name", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "incident_id", "channel", "channel_name", "event", "status", "attempts",
            "created_at", "sent_at", "error",
        ]  # fmt: skip
