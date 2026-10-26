from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.heartbeats.models import HeartbeatJob
from apps.registry.models import Server


class Command(BaseCommand):
    help = (
        "Heartbeat ishi yaratadi va tokenini bir marta ko'rsatadi (masalan, appctl-backup@main-2)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name")
        parser.add_argument("--every", type=int, default=86400, help="kutilgan oraliq, soniya")
        parser.add_argument("--grace", type=int, default=7200, help="kechikish zaxirasi, soniya")
        parser.add_argument("--server", help="server nomi (ixtiyoriy)")

    def handle(self, *args: Any, **options: Any) -> None:
        server = Server.objects.get(name=options["server"]) if options["server"] else None
        job, token = HeartbeatJob.issue(
            options["name"], options["every"], grace_s=options["grace"], server=server
        )
        self.stdout.write(
            f"heartbeat ishi: {job.name} (har {job.expected_every_s} s, zaxira {job.grace_s} s)"
        )
        self.stdout.write(f"URL yo'li (qayta ko'rsatilmaydi): /hb/{token}")
