import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.core.leader import Leader
from apps.probes.services import run_due

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Prober: vaqti kelgan tekshiruvlarni parallel bajaradi (TZ 6.8)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="bir marta o'tib chiqib to'xtash")
        parser.add_argument("--interval", type=float, default=1.0, help="so'rov oralig'i, soniya")

    def handle(self, *args: Any, **options: Any) -> None:
        leader = Leader("prober")
        while True:
            started = time.monotonic()
            if not options["once"] and not leader.ensure():
                time.sleep(max(0.0, options["interval"] - (time.monotonic() - started)))
                continue
            try:
                done = run_due()
                if done:
                    self.stdout.write(f"bajarildi: {done}")
            except Exception:
                logger.exception("prober davri muvaffaqiyatsiz")
                if options["once"]:
                    raise
            if options["once"]:
                return
            time.sleep(max(0.0, options["interval"] - (time.monotonic() - started)))
