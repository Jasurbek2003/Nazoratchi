import time
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.backups import selfbackup
from apps.backups.models import SelfBackup


class Command(BaseCommand):
    help = (
        "Nazoratchi o'z zaxirasini oladi, `age` bilan shifrlaydi va Telegram'da Owner'ning shaxsiy chatiga yuboradi "
        "(FR-SYS-003). --loop: har kuni --hour (UTC) da."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--channel",
            default="owner-backup",
            help="shaxsiy chat kanali nomi (standart owner-backup)",
        )
        parser.add_argument("--loop", action="store_true", help="har kuni takrorlash")
        parser.add_argument(
            "--hour", type=int, default=3, help="--loop uchun soat (UTC), standart 3"
        )

    def _once(self, channel: str) -> bool:
        try:
            record = selfbackup.run(channel)
        except selfbackup.SelfBackupError as exc:
            # Sozlash xatosi ham qayd etiladi: kunlik alert (AL-091) ko'rsin
            SelfBackup.objects.create(
                status=SelfBackup.Status.FAILED, error=str(exc)[:300], channel_name=channel
            )
            self.stderr.write(f"xato: {exc}")
            return False
        if record.status == SelfBackup.Status.OK:
            self.stdout.write(f"yuborildi: {record.size_bytes} bayt, {record.parts} bo'lak")
            return True
        self.stderr.write(f"yuborilmadi: {record.error}")
        return False

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["loop"]:
            if not self._once(options["channel"]):
                raise CommandError("o'z zaxirasi yuborilmadi")
            return
        if not 0 <= options["hour"] <= 23:
            raise CommandError("--hour 0..23 bo'lishi kerak")
        while True:
            now = timezone.now()
            nxt = now.replace(hour=options["hour"], minute=0, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
            time.sleep((nxt - now).total_seconds())
            self._once(options["channel"])
