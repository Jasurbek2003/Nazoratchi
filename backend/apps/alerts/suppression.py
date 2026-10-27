"""Bostirish (TZ 6.7.3, 12.5, 12.6): pause > maintenance > silence; bog'liqlik bo'yicha va ahamiyat bo'yicha.

Bostirilgan alert yo'qolmaydi: holat hisoblanaveradi, incident ochiladi, faqat bildirishnoma yuborilmaydi.
Bostirish sababi yo'qolsa (silence tugadi, host qaytdi) va shart hamon rost bo'lsa, xabar yuboriladi.
"""

import re
from datetime import datetime
from typing import Any

from apps.notifications.models import SEVERITY_RANK
from apps.registry.models import ProjectServer, Server

from .models import AlertInstance, MaintenanceWindow, Silence

MATCHER_LABELS = {"server", "project", "rule", "severity", "tag", "domain", "container"}
MATCHER_OPS = {"=", "!=", "=~"}
MAX_REGEX_LEN = 100
HOST_DOWN_KEY = "AL-001"
MASS_SILENCE_KEY = "AL-008"
SILENCE_DEPENDENT_EXEMPT = {
    "AL-001",
    "AL-002",
    "AL-008",
}  # host o'chganda bostirilmaydigan "sabab" alertlari
PROBE_SUBJECTS = ("probe", "cert", "backup")
DNS_KEYS = {"AL-062", "AL-063"}


def supersede_group(rule: Any) -> str | None:
    """Bir obyektdagi bir kattalikning bir nechta chegara qoidasi guruhi: eng og'iri xabar beradi."""
    cond = rule.condition
    if cond.get("type") == "threshold":
        return str(cond.get("metric"))
    if (
        cond.get("type") == "state"
        and cond.get("source") == "cert"
        and cond.get("field") == "days_left_lte"
    ):
        return "cert_days_left"
    if (
        cond.get("type") == "state"
        and cond.get("source") == "backup"
        and cond.get("field") == "age_hours_gt"
    ):
        return "backup_age"
    return None


class MatcherError(ValueError):
    pass


def validate_matchers(matchers: Any) -> None:
    if not isinstance(matchers, list) or not 1 <= len(matchers) <= 10:
        raise MatcherError("matchers 1..10 elementli ro'yxat bo'lishi kerak")
    for m in matchers:
        if not isinstance(m, dict) or set(m) != {"label", "op", "value"}:
            raise MatcherError("har matcher {label, op, value} bo'lishi kerak")
        if m["label"] not in MATCHER_LABELS:
            raise MatcherError(f"label {', '.join(sorted(MATCHER_LABELS))} dan biri bo'lishi kerak")
        if m["op"] not in MATCHER_OPS:
            raise MatcherError("op =, != yoki =~ bo'lishi kerak")
        if not isinstance(m["value"], str) or not 1 <= len(m["value"]) <= MAX_REGEX_LEN:
            raise MatcherError(f"value 1..{MAX_REGEX_LEN} belgili matn bo'lishi kerak")
        if m["op"] == "=~":
            try:
                re.compile(m["value"])
            except re.error as exc:
                raise MatcherError(f"regex noto'g'ri: {exc}") from exc


def matches(matchers: list[dict[str, str]], labels: dict[str, list[str]]) -> bool:
    """Hamma matcher mos kelsa True. Ko'p qiymatli etiket (project, tag) uchun: `=` va `=~` — birortasi,
    `!=` — hech biri."""
    for m in matchers:
        values = labels.get(m["label"], [])
        if m["op"] == "=":
            ok = m["value"] in values
        elif m["op"] == "!=":
            ok = m["value"] not in values
        else:
            ok = any(re.fullmatch(m["value"], v) for v in values)
        if not ok:
            return False
    return True


class SuppressionContext:
    """Bir bildirishnoma bosqichi uchun holat: faol silence/maintenance va kerakli qidiruvlar."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.silences = list(
            Silence.objects.filter(cancelled_at__isnull=True, starts_at__lte=now, ends_at__gt=now)
        )
        self.windows = list(
            MaintenanceWindow.objects.filter(
                cancelled_at__isnull=True, starts_at__lte=now, ends_at__gt=now
            )
        )
        firing = list(
            AlertInstance.objects.filter(state=AlertInstance.State.FIRING).select_related("rule")
        )
        self.host_down = {i.subject_id for i in firing if i.rule.key == HOST_DOWN_KEY}
        self.mass_silence = any(i.rule.key == MASS_SILENCE_KEY for i in firing)
        self.top_rank: dict[tuple[str, str], int] = {}
        for i in firing:
            metric = supersede_group(i.rule)
            if metric:
                key = (i.subject_id, metric)
                self.top_rank[key] = max(self.top_rank.get(key, -1), SEVERITY_RANK[i.rule.severity])
        self._servers: dict[str, Server] = {}
        self._projects: dict[str, list[tuple[str, str]]] = {}
        ids = {i.subject_id.split(":")[0] for i in firing if i.subject_type == "host"}
        # Faol tekshiruv (probe) alertlari: loyihaning serverlari bostirish uchun kerak.
        probe_projects = {
            i.labels.get("project_id") for i in firing if i.subject_type in PROBE_SUBJECTS
        } - {None, ""}
        # Domen DNS si mos emas: shu domenning HTTP/TLS alertlari bostiriladi (sabab bitta, 6.7.3).
        self.dns_domains = {i.labels.get("domain") for i in firing if i.rule.key in DNS_KEYS} - {
            None,
            "",
        }
        self._project_servers: dict[str, set[str]] = {}
        for row in ProjectServer.objects.filter(project_id__in=probe_projects):
            self._project_servers.setdefault(str(row.project_id), set()).add(str(row.server_id))
        ids |= {sid for servers in self._project_servers.values() for sid in servers}
        for server in Server.objects.filter(pk__in=ids):
            self._servers[str(server.pk)] = server
        for row in ProjectServer.objects.filter(server_id__in=ids).select_related("project"):
            self._projects.setdefault(str(row.server_id), []).append(
                (str(row.project_id), row.project.name)
            )

    def _in_maintenance(self, server_id: str) -> bool:
        project_ids = {pid for pid, _ in self._projects.get(server_id, [])}
        for w in self.windows:
            if server_id in {str(x) for x in w.scope.get("servers", [])}:
                return True
            if project_ids & {str(x) for x in w.scope.get("projects", [])}:
                return True
        return False

    def _probe_servers(self, inst: AlertInstance) -> set[str]:
        return self._project_servers.get(inst.labels.get("project_id", ""), set())

    def labels_for(self, inst: AlertInstance) -> dict[str, list[str]]:
        labels = {"rule": [inst.rule.key], "severity": [inst.rule.severity]}
        if inst.subject_type in PROBE_SUBJECTS:
            if inst.labels.get("project"):
                labels["project"] = [inst.labels["project"]]
            if inst.labels.get("domain"):
                labels["domain"] = [inst.labels["domain"]]
            names = [self._servers[s].name for s in self._probe_servers(inst) if s in self._servers]
            if names:
                labels["server"] = names
            return labels
        server = (
            self._servers.get(inst.subject_id.split(":")[0])
            if inst.subject_type == "host"
            else None
        )
        if server is not None:
            labels["server"] = [server.name]
            labels["tag"] = list(server.tags)
            labels["project"] = [name for _, name in self._projects.get(str(server.pk), [])]
            for key in ("container", "domain"):
                if inst.labels.get(key):
                    labels[key] = [inst.labels[key]]
        return labels

    def _probe_reason(self, inst: AlertInstance) -> str:
        """Tekshiruv alerti: loyihaning HAMMA serveri pauzada / texnik ishda / o'chgan bo'lsa bostiriladi (6.7.3)."""
        servers = self._probe_servers(inst)
        project_id = inst.labels.get("project_id", "")
        in_window = any(
            project_id in {str(x) for x in w.scope.get("projects", [])} for w in self.windows
        )
        if servers and all(
            self._servers[s].status == Server.Status.PAUSED for s in servers if s in self._servers
        ):
            return "pause"
        if in_window or (servers and all(self._in_maintenance(s) for s in servers)):
            return "maintenance"
        if self.silences:
            labels = self.labels_for(inst)
            if any(matches(s.matchers, labels) for s in self.silences):
                return "silence"
        if servers and servers <= self.host_down:
            return "host_down"
        if inst.rule.key not in DNS_KEYS and inst.labels.get("domain") in self.dns_domains:
            return "dns_mismatch"
        metric = supersede_group(inst.rule)
        if (
            metric
            and self.top_rank.get((inst.subject_id, metric), -1) > SEVERITY_RANK[inst.rule.severity]
        ):
            return "superseded"
        return ""

    def reason(self, inst: AlertInstance) -> str:
        """Bostirish sababi yoki '' (yuborish kerak). Ustuvorlik: pause > maintenance > silence > bog'liqlik."""
        rule = inst.rule
        if inst.subject_type in PROBE_SUBJECTS:
            return self._probe_reason(inst)
        server_id = inst.subject_id.split(":")[0] if inst.subject_type == "host" else ""
        server = self._servers.get(server_id)
        if server is not None and server.status == Server.Status.PAUSED:
            return "pause"
        if server_id and self._in_maintenance(server_id):
            return "maintenance"
        if self.silences:
            labels = self.labels_for(inst)
            if any(matches(s.matchers, labels) for s in self.silences):
                return "silence"
        if server_id and rule.key not in SILENCE_DEPENDENT_EXEMPT and server_id in self.host_down:
            return "host_down"
        if self.mass_silence and rule.key in {"AL-001", "AL-002"}:
            return "mass_silence"
        metric = supersede_group(rule)
        if (
            metric
            and self.top_rank.get((inst.subject_id, metric), -1) > SEVERITY_RANK[rule.severity]
        ):
            return "superseded"
        return ""
