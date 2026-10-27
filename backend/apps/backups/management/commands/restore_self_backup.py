from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.backups import selfbackup


class Command(BaseCommand):
    help = (
        "O'z zaxirasini tiklaydi (yangi serverda). Bo'laklar tartibda beriladi. Maxfiy `age` kaliti faylda (AGE-SECRET-KEY-...). "
        "Mavjud yozuvlar (bir xil id) YANGILANADI: faqat bo'sh/yangi bazaga tiklash tavsiya etiladi."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "files", nargs="+", help="*.age fayl yoki .partNNofMM bo'laklari (tartibda)"
        )
        parser.add_argument("--identity", required=True, help="maxfiy kalit fayli")
        parser.add_argument("--yes", action="store_true", help="bazani o'zgartirishni tasdiqlash")

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["yes"]:
            raise CommandError(
                "Baza o'zgaradi. Davom etish uchun --yes bering (avval bo'sh bazada sinab ko'ring)."
            )
        try:
            identity = Path(options["identity"]).read_text(encoding="utf-8")
            parts = [Path(f).read_bytes() for f in options["files"]]
        except OSError as exc:
            raise CommandError(f"fayl o'qilmadi: {exc}") from exc
        try:
            result = selfbackup.restore(
                parts,
                "".join(
                    line for line in identity.splitlines() if line.startswith("AGE-SECRET-KEY-")
                ),
            )
        except selfbackup.SelfBackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(result or "tiklandi")
