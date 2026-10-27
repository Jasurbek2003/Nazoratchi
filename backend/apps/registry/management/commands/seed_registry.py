"""Boshlang'ich reyestrni `seed/inventory.yaml` dan yuklash (TZ 18.5, B2).

Idempotent: mavjud serverlar/loyihalar/domenlar/heartbeat'larga TEGILMAYDI (foydalanuvchi o'zgartirgan bo'lishi
mumkin); faqat yo'qlari yaratiladi. Heartbeat tokenlari faqat yaratilganda, bir marta chop etiladi.
"""

from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.heartbeats.models import HeartbeatJob
from apps.probes.models import Probe
from apps.probes.services import ensure_domain_probes
from apps.registry.models import Domain, Project, ProjectServer, Server, Setting
from apps.registry.projects import normalize_fqdn


class Command(BaseCommand):
    help = "Boshlang'ich reyestrni yuklaydi (yo'qlarini yaratadi, mavjudga tegmaydi)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--file", default=str(Path(settings.BASE_DIR).parent / "seed" / "inventory.yaml")
        )
        parser.add_argument("--dry-run", action="store_true", help="hech narsa saqlamasdan hisobot")
        parser.add_argument(
            "--auto-probes",
            action="store_true",
            help="har domen uchun HTTP tekshiruv yaratish (haqiqiy so'rovlar ketadi)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"Fayl topilmadi: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise CommandError("inventory.yaml: version: 1 kutilgan")
        counts: dict[str, int] = {}
        tokens: list[str] = []
        with transaction.atomic():
            servers = self._servers(data.get("servers", []), counts)
            if data.get("retired_ips"):  # DNS tekshiruvlari (AL-063) shu ro'yxatdan foydalanadi
                _, made = Setting.objects.get_or_create(
                    key="retired_ips", defaults={"value": data["retired_ips"]}
                )
                if made:
                    self._bump(counts, "retired_ips")
            self._projects(data.get("projects", []), servers, counts, options["auto_probes"])
            self._heartbeats(data.get("heartbeats", []), servers, counts, tokens)
            if options["dry_run"]:
                transaction.set_rollback(True)
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            prefix + ", ".join(f"{k}: +{v}" for k, v in counts.items()) or "yangi narsa yo'q"
        )
        for line in tokens if not options["dry_run"] else []:
            self.stdout.write(line)

    def _bump(self, counts: dict[str, int], key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    def _servers(self, rows: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, Server]:
        out = {}
        for row in rows:
            server, created = Server.objects.get_or_create(
                name=row["name"],
                defaults={
                    "provider": row.get("provider", ""), "public_ipv4": row.get("public_ipv4") or None,
                    "role": row.get("role", ""), "tags": row.get("tags", []),
                    "status": row.get("status", Server.Status.NEW),
                },
            )  # fmt: skip
            out[server.name] = server
            if created:
                self._bump(counts, "serverlar")
        return out

    def _projects(
        self,
        rows: list[dict[str, Any]],
        servers: dict[str, Server],
        counts: dict[str, int],
        auto_probes: bool,
    ) -> None:
        for row in rows:
            project, created = Project.objects.get_or_create(
                slug=row["slug"],
                defaults={
                    "name": row["name"],
                    "kind": row.get("kind", "other"),
                    "moved": row.get("moved", True),
                },
            )
            if created:
                self._bump(counts, "loyihalar")
            expected_ips: list[
                str
            ] = []  # domenlar loyihaning production serveri IP siga qarashi kutiladi
            for link in row.get("servers", []):
                server = (
                    servers.get(link["server"])
                    or Server.objects.filter(name=link["server"]).first()
                )
                if server is None:
                    raise CommandError(f"{project.slug}: server topilmadi: {link['server']}")
                _, linked = ProjectServer.objects.get_or_create(
                    project=project, server=server, environment=link.get("environment", "production"),
                    defaults={"ports": link.get("ports", [])},
                )  # fmt: skip
                if linked:
                    self._bump(counts, "biriktirishlar")
                if link.get("environment", "production") == "production" and server.public_ipv4:
                    expected_ips.append(str(server.public_ipv4))
            for d in row.get("domains", []):
                domain, made = Domain.objects.get_or_create(
                    fqdn=normalize_fqdn(d["fqdn"]),
                    defaults={
                        "project": project, "dns_provider": d.get("dns_provider", ""),
                        "controlled_by": d.get("controlled_by", "self"),
                        "expected_ips": expected_ips,
                    },
                )  # fmt: skip
                if made:
                    self._bump(counts, "domenlar")
                if auto_probes and project.moved:
                    for probe in ensure_domain_probes(domain):
                        if probe.type == "http" and d.get("primary"):
                            probe.config = {**probe.config, "primary": True}
                            probe.save(update_fields=["config"])
                        self._bump(counts, "tekshiruvlar")
            for p in row.get("probes", []):
                url = p["url"]
                if not Probe.objects.filter(
                    project=project, type=p["type"], config__url=url
                ).exists():
                    Probe.objects.create(
                        project=project, type=p["type"], name=p.get("name", f"{project.slug} {p['type']}"),
                        config={"url": url, "expected_status": p.get("expected_status", [200]), "primary": True},
                    )  # fmt: skip
                    self._bump(counts, "tekshiruvlar")

    def _heartbeats(
        self,
        rows: list[dict[str, Any]],
        servers: dict[str, Server],
        counts: dict[str, int],
        tokens: list[str],
    ) -> None:
        for row in rows:
            if HeartbeatJob.objects.filter(name=row["name"]).exists():
                continue
            server = (
                servers.get(row.get("server", ""))
                or Server.objects.filter(name=row.get("server", "")).first()
            )
            job, token = HeartbeatJob.issue(
                row["name"],
                row["expected_every_s"],
                grace_s=row.get("grace_s", 3600),
                server=server,
            )
            tokens.append(f"heartbeat {job.name}: /hb/{token}  (qayta ko'rsatilmaydi)")
            self._bump(counts, "heartbeat")
