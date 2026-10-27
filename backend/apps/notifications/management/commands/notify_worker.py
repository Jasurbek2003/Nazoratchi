import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.notifications.services import deliver_due


class Command(BaseCommand):
    help = (
        "Navbatdagi bildirishnomalarni yuboradi (qayta urinishlar bilan). S3 da evaluator worker "
        "shu `deliver_due()` ni chaqiradi; shu vaqtgacha alohida jarayon sifatida ishga tushiriladi."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="bir marta o'tib chiqib to'xtash")
        parser.add_argument("--interval", type=float, default=2.0, help="soniya (standart 2)")

    def handle(self, *args: Any, **options: Any) -> None:
        while True:
            sent = deliver_due()
            if sent:
                self.stdout.write(f"urinishlar: {sent}")
            if options["once"]:
                return
            time.sleep(options["interval"])
