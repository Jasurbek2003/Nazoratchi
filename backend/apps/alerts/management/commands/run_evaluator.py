import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.alerts.engine import run_cycle

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Alert dvigatelini ishga tushiradi: har davrda qoidalarni hisoblab, incidentlarni yuritadi (TZ 6.7)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="bir davr hisoblab to'xtash")
        parser.add_argument(
            "--interval", type=float, default=15.0, help="davr, soniya (standart 15)"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        while True:
            started = time.monotonic()
            try:
                stats = run_cycle()
                self.stdout.write(f"davr: {stats}")
            except Exception:
                # Dvigatel hech qachon yiqilmasligi kerak: xato logga, keyingi davrda qayta uriniladi.
                logger.exception("alert davri muvaffaqiyatsiz")
                if options["once"]:
                    raise
            if options["once"]:
                return
            time.sleep(max(0.0, options["interval"] - (time.monotonic() - started)))
