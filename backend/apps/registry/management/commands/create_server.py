from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.registry.models import AgentToken, Server


class Command(BaseCommand):
    help = "Server yaratadi va agent tokenini bir marta ko'rsatadi (prototip; enroll oqimi B3 da)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name")

    def handle(self, *args: Any, **options: Any) -> None:
        server, created = Server.objects.get_or_create(name=options["name"])
        _, token = AgentToken.issue(server)
        self.stdout.write(
            f"server: {server.name} ({server.id}) {'yaratildi' if created else 'mavjud'}"
        )
        self.stdout.write(f"token (qayta ko'rsatilmaydi): {token}")
