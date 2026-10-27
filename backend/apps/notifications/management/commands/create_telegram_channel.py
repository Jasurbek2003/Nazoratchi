import getpass
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.audit.services import record
from apps.notifications.models import SEVERITIES, Channel
from apps.notifications.serializers import _validate_telegram_config


class Command(BaseCommand):
    help = (
        "Telegram kanalini yaratadi (birinchi sozlash uchun). Bot tokeni terminalda so'raladi "
        "yoki NAZORATCHI_TELEGRAM_BOT_TOKEN dan olinadi; buyruq satriga yozilmaydi."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name")
        parser.add_argument("--chat-id", required=True, help="son (-100... guruh) yoki @kanal")
        parser.add_argument("--min-severity", default="warning", choices=SEVERITIES)

    def handle(self, *args: Any, **options: Any) -> None:
        if Channel.objects.filter(name=options["name"]).exists():
            raise CommandError(f"Kanal mavjud: {options['name']}")
        token = os.environ.get("NAZORATCHI_TELEGRAM_BOT_TOKEN") or getpass.getpass("Bot tokeni: ")
        raw_chat: str = options["chat_id"]
        chat: int | str = int(raw_chat) if raw_chat.lstrip("-").isdigit() else raw_chat
        from rest_framework.serializers import ValidationError

        try:
            config = _validate_telegram_config({"bot_token": token, "chat_id": chat}, partial=False)
        except ValidationError as exc:
            raise CommandError(" ".join(str(m) for m in exc.detail)) from exc
        channel = Channel(
            type=Channel.Type.TELEGRAM, name=options["name"], min_severity=options["min_severity"]
        )
        channel.set_config(config)
        channel.save()
        record(
            "channel.create",
            object_type="channel",
            object_id=channel.id,
            after={"name": channel.name, "type": "telegram", "min_severity": channel.min_severity},
        )
        self.stdout.write(f"Kanal yaratildi: {channel.name} ({channel.id})")
