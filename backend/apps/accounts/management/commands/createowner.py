import getpass
import os
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.audit.services import record


class Command(BaseCommand):
    help = "Birinchi Owner'ni yaratadi (TZ 15.7). Parol terminalda so'raladi (yoki NAZORATCHI_OWNER_PASSWORD)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--login", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        login = options["login"]
        if User.objects.filter(login=login).exists():
            raise CommandError(f"Foydalanuvchi mavjud: {login}")
        password = os.environ.get("NAZORATCHI_OWNER_PASSWORD") or getpass.getpass("Parol: ")
        if "NAZORATCHI_OWNER_PASSWORD" not in os.environ and password != getpass.getpass(
            "Parolni takrorlang: "
        ):
            raise CommandError("Parollar mos kelmadi.")
        probe = User(login=login, role=User.Role.OWNER)
        try:
            validate_password(password, probe)
        except ValidationError as exc:
            raise CommandError(
                "Parol talablarga javob bermaydi: " + " ".join(exc.messages)
            ) from exc
        user = User.objects.create_user(login, password, role=User.Role.OWNER)
        record(
            "user.create",
            object_type="user",
            object_id=user.id,
            after={"login": login, "role": "owner"},
        )
        self.stdout.write(f"Owner yaratildi: {login}")
