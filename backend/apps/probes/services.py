"""Tekshiruvlarni rejalash, bajarish va holatini yuritish (TZ 6.8).

Tasdiqlash qoidasi: muvaffaqiyatsiz natijadan keyin 15 s oraliq bilan qayta tekshiriladi; 3 ketma-ket xato = `down`;
bitta muvaffaqiyat = `up`. Qayta tekshiruv oqim ichida uxlamaydi: `next_run_at` 15 s ga suriladi.
"""

import ipaddress
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from apps.registry.models import Domain, Setting

from . import checks
from .models import CertStatus, DnsChange, Probe

logger = logging.getLogger(__name__)

CONFIRM_FAILURES = 3
RETRY_S = 15
MAX_WORKERS = 50
CLAIM_LIMIT = 200
HTTP_KEYS = {
    "url", "method", "expected_status", "keyword", "follow_redirects", "max_redirects", "headers",
    "verify_tls", "resolve_to", "latency_warn_ms", "max_body_bytes", "allow_private", "primary",
}  # fmt: skip
TCP_KEYS = {"host", "port", "expect", "allow_private", "primary"}
TLS_KEYS = {
    "host",
    "port",
    "sni",
    "warn_days",
    "high_days",
    "critical_days",
    "check_chain",
    "check_hostname",
    "allow_private",
    "primary",
}
DNS_KEYS = {
    "name",
    "rtype",
    "resolvers",
    "expected",
    "retired_ips",
    "mismatch_after_min",
    "allow_private",
    "primary",
}


class ProbeConfigError(ValueError):
    pass


def validate_config(kind: str, config: Any) -> None:
    """Sxema 18.4 (http, tcp). Noma'lum kalit rad etiladi."""
    if not isinstance(config, dict):
        raise ProbeConfigError("config obyekt bo'lishi kerak")
    if kind == "http":
        _check_http(config)
    elif kind == "tcp":
        _check_tcp(config)
    elif kind == "tls":
        _check_tls(config)
    elif kind == "dns":
        _check_dns(config)
    else:
        raise ProbeConfigError(f"{kind} turi hali qo'llab-quvvatlanmaydi (whois — F2)")


def _unknown(config: dict[str, Any], allowed: set[str]) -> None:
    if extra := set(config) - allowed:
        raise ProbeConfigError(f"noma'lum kalitlar: {', '.join(sorted(extra))}")


def _check_http(c: dict[str, Any]) -> None:
    from urllib.parse import urlsplit

    _unknown(c, HTTP_KEYS)
    parts = urlsplit(str(c.get("url", "")))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ProbeConfigError("url http(s):// bilan boshlanib, host bo'lishi kerak")
    if parts.username or parts.password:
        raise ProbeConfigError("url ichida login/parol bo'lmasligi kerak")
    if c.get("method", "GET") not in ("GET", "HEAD"):
        raise ProbeConfigError("method GET yoki HEAD bo'lishi kerak")
    expected = c.get("expected_status", [200])
    if not isinstance(expected, list) or not expected:
        raise ProbeConfigError("expected_status bo'sh bo'lmagan ro'yxat bo'lishi kerak")
    try:
        ranges = checks.parse_expected(expected)
    except (ValueError, TypeError) as exc:
        raise ProbeConfigError("expected_status: son yoki '200-299' ko'rinishida") from exc
    if not all(100 <= lo <= hi <= 599 for lo, hi in ranges):
        raise ProbeConfigError("expected_status 100..599 oralig'ida bo'lishi kerak")
    keyword = c.get("keyword")
    if keyword is not None and not (
        isinstance(keyword, dict)
        and isinstance(keyword.get("text"), str)
        and 1 <= len(keyword["text"]) <= 200
        and keyword.get("mode", "contains") in ("contains", "not_contains")
    ):
        raise ProbeConfigError("keyword {text, mode: contains|not_contains} bo'lishi kerak")
    headers = c.get("headers") or {}
    if (
        not isinstance(headers, dict)
        or len(headers) > 10
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items())
    ):
        raise ProbeConfigError("headers {matn: matn} (≤ 10 ta) bo'lishi kerak")
    if any(k.lower() in ("host", "content-length", "transfer-encoding") for k in headers):
        raise ProbeConfigError("Host/Content-Length sarlavhalarini o'zgartirib bo'lmaydi")
    for key, lo, hi in (
        ("max_redirects", 0, 10),
        ("latency_warn_ms", 1, 600000),
        ("max_body_bytes", 1, 1 << 20),
    ):
        if key in c and (
            isinstance(c[key], bool) or not isinstance(c[key], int) or not lo <= c[key] <= hi
        ):
            raise ProbeConfigError(f"{key} {lo}..{hi} oralig'ida butun son bo'lishi kerak")
    for key in ("follow_redirects", "verify_tls", "allow_private", "primary"):
        if key in c and not isinstance(c[key], bool):
            raise ProbeConfigError(f"{key} true/false bo'lishi kerak")
    if c.get("resolve_to") is not None:
        try:
            ipaddress.ip_address(c["resolve_to"])
        except ValueError as exc:
            raise ProbeConfigError("resolve_to IP manzil bo'lishi kerak") from exc


def _check_tls(c: dict[str, Any]) -> None:
    _unknown(c, TLS_KEYS)
    for key in ("host", "sni"):
        if key in c and (not isinstance(c[key], str) or not c[key] or len(c[key]) > 253):
            raise ProbeConfigError(f"{key} domen nomi bo'lishi kerak")
    if "host" not in c:
        raise ProbeConfigError("host majburiy")
    if "port" in c and (
        isinstance(c["port"], bool) or not isinstance(c["port"], int) or not 1 <= c["port"] <= 65535
    ):
        raise ProbeConfigError("port 1..65535 bo'lishi kerak")
    for key in ("warn_days", "high_days", "critical_days"):
        if key in c and (
            isinstance(c[key], bool) or not isinstance(c[key], int) or not 0 <= c[key] <= 365
        ):
            raise ProbeConfigError(f"{key} 0..365 bo'lishi kerak")
    for key in ("check_chain", "check_hostname", "allow_private", "primary"):
        if key in c and not isinstance(c[key], bool):
            raise ProbeConfigError(f"{key} true/false bo'lishi kerak")


def _ips(value: Any, key: str, limit: int = 20) -> None:
    if not isinstance(value, list) or len(value) > limit:
        raise ProbeConfigError(f"{key} IP manzillar ro'yxati (≤ {limit}) bo'lishi kerak")
    for item in value:
        try:
            ipaddress.ip_address(item)
        except ValueError as exc:
            raise ProbeConfigError(f"{key}: {item!r} IP manzil emas") from exc


def _check_dns(c: dict[str, Any]) -> None:
    _unknown(c, DNS_KEYS)
    name = c.get("name")
    if not isinstance(name, str) or "." not in name or len(name) > 253:
        raise ProbeConfigError("name domen nomi bo'lishi kerak")
    if c.get("rtype", "A") not in ("A", "AAAA"):
        raise ProbeConfigError("rtype A yoki AAAA bo'lishi kerak")
    resolvers = c.get("resolvers", [])
    if not isinstance(resolvers, list) or len(resolvers) > 6:
        raise ProbeConfigError("resolvers ro'yxati (≤ 6) bo'lishi kerak")
    for r in resolvers:
        if r == "ns:auto":
            continue
        try:
            ip = ipaddress.ip_address(r)
        except ValueError as exc:
            raise ProbeConfigError(f"resolver {r!r}: IP yoki 'ns:auto' bo'lishi kerak") from exc
        if checks.is_blocked(str(ip)) and not c.get("allow_private"):
            raise ProbeConfigError(f"resolver {r} ichki manzil (SSRF)")
    _ips(c.get("expected", []), "expected")
    _ips(c.get("retired_ips", []), "retired_ips")
    if "mismatch_after_min" in c and (
        isinstance(c["mismatch_after_min"], bool)
        or not isinstance(c["mismatch_after_min"], int)
        or not 1 <= c["mismatch_after_min"] <= 1440
    ):
        raise ProbeConfigError("mismatch_after_min 1..1440 bo'lishi kerak")
    for key in ("allow_private", "primary"):
        if key in c and not isinstance(c[key], bool):
            raise ProbeConfigError(f"{key} true/false bo'lishi kerak")


def _check_tcp(c: dict[str, Any]) -> None:
    _unknown(c, TCP_KEYS)
    if not isinstance(c.get("host"), str) or not c["host"] or len(c["host"]) > 253:
        raise ProbeConfigError("host majburiy")
    if (
        isinstance(c.get("port"), bool)
        or not isinstance(c.get("port"), int)
        or not 1 <= c["port"] <= 65535
    ):
        raise ProbeConfigError("port 1..65535 bo'lishi kerak")
    if c.get("expect", "open") not in ("open", "closed"):
        raise ProbeConfigError("expect open yoki closed bo'lishi kerak")
    for key in ("allow_private", "primary"):
        if key in c and not isinstance(c[key], bool):
            raise ProbeConfigError(f"{key} true/false bo'lishi kerak")


# ----------------------------------------------------------------------- natijalar
def store_result(probe: Probe, now: datetime, outcome: checks.Outcome) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO probe_results
              (time, probe_id, ok, status_code, total_ms, dns_ms, connect_ms, tls_ms, ttfb_ms, error_kind, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                now, probe.pk, outcome.ok, outcome.status_code, outcome.total_ms, outcome.dns_ms,
                outcome.connect_ms, outcome.tls_ms, outcome.ttfb_ms, outcome.error_kind,
                json.dumps(outcome.detail) if outcome.detail else None,
            ],
        )  # fmt: skip


def jitter(seconds: int) -> timedelta:
    return timedelta(seconds=seconds * random.uniform(0.9, 1.1))  # noqa: S311 (taqsimlash, kriptografiya emas)


def apply_outcome(probe: Probe, outcome: checks.Outcome, now: datetime) -> None:
    """Tasdiqlash qoidasi va keyingi ishga tushirish vaqti. Saqlashni ham bajaradi."""
    old_state = probe.state
    probe.last_run_at = now
    if outcome.ok:
        probe.consecutive_failures, probe.state = 0, Probe.State.UP
        probe.next_run_at = now + jitter(probe.interval_s)
    else:
        probe.consecutive_failures = min(probe.consecutive_failures + 1, 255)
        if probe.consecutive_failures >= CONFIRM_FAILURES:
            probe.state = Probe.State.DOWN
            probe.next_run_at = now + jitter(probe.interval_s)
        else:  # tasdiqlanmagan: tezroq qayta tekshiriladi, holat o'zgarmaydi
            probe.next_run_at = now + timedelta(seconds=min(RETRY_S, probe.interval_s))
    if probe.state != old_state:
        probe.state_since = now
    probe.save(
        update_fields=["last_run_at", "consecutive_failures", "state", "state_since", "next_run_at"]
    )
    store_result(probe, now, outcome)
    record_extras(probe, outcome, now)


def record_extras(probe: Probe, outcome: checks.Outcome, now: datetime) -> None:
    """Tur bo'yicha qo'shimcha saqlash: TLS -> cert_status; DNS -> dns_results va o'zgarishlar tarixi."""
    if probe.type == Probe.Type.TLS and outcome.ok and "not_after" in outcome.detail:
        d = outcome.detail
        CertStatus.objects.update_or_create(
            name=probe.config.get("sni") or probe.config["host"], source=CertStatus.Source.PROBE, server=None,
            defaults={
                "domain": probe.domain, "not_after": datetime.fromisoformat(d["not_after"]), "issuer": d["issuer"],
                "subject": d["subject"], "san": d["san"], "chain_ok": d["chain_ok"], "hostname_ok": d["hostname_ok"],
                "checked_at": now,
            },
        )  # fmt: skip
    elif probe.type == Probe.Type.DNS and probe.domain_id and "resolvers" in outcome.detail:
        rtype = probe.config.get("rtype", "A")
        with connection.cursor() as cursor:
            for r in outcome.detail["resolvers"]:
                if r["rcode"] in ("TIMEOUT", "ERROR", "BLOCKED", "NO_NS"):
                    continue  # javob yo'q: o'zgarish emas
                cursor.execute(
                    "SELECT answers FROM dns_results WHERE probe_id = %s AND resolver = %s ORDER BY time DESC LIMIT 1",
                    [probe.pk, r["resolver"]],
                )
                previous = cursor.fetchone()
                cursor.execute(
                    "INSERT INTO dns_results (time, domain_id, probe_id, resolver, rtype, answers, matches, rcode, latency_ms)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        now,
                        probe.domain_id,
                        probe.pk,
                        r["resolver"],
                        rtype,
                        r["answers"],
                        r["matches"],
                        r["rcode"],
                        r["latency_ms"],
                    ],
                )
                if previous is not None and list(previous[0]) != r["answers"]:
                    DnsChange.objects.create(
                        domain_id=probe.domain_id, resolver=r["resolver"], rtype=rtype,
                        old_answers=list(previous[0]), new_answers=r["answers"], changed_at=now,
                    )  # fmt: skip


def execute(probe: Probe) -> checks.Outcome:
    try:
        return checks.run_check(probe.type, probe.config, probe.timeout_s)
    except Exception:
        logger.exception("tekshiruv kutilmagan xato bilan tugadi: %s", probe.name)
        return checks.Outcome(False, error_kind="config", detail={"error": "ichki xato"})


def run_due(now: datetime | None = None, limit: int = CLAIM_LIMIT) -> int:
    """Vaqti kelgan tekshiruvlarni parallel bajaradi. Qaytadi: bajarilganlar soni.
    Avval `next_run_at` surib qo'yiladi (bir nechta prober bir tekshiruvni takrorlamaydi), keyin bajariladi."""
    now = now or timezone.now()
    with transaction.atomic():
        due = list(
            Probe.objects.select_for_update(skip_locked=True)
            .filter(enabled=True, next_run_at__lte=now)
            .order_by("next_run_at")[:limit]
        )
        for probe in due:
            Probe.objects.filter(pk=probe.pk).update(
                next_run_at=now + timedelta(seconds=probe.interval_s + probe.timeout_s)
            )
    if not due:
        return 0
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(due))) as pool:
        outcomes = list(pool.map(execute, due))
    for probe, outcome in zip(due, outcomes, strict=True):
        apply_outcome(probe, outcome, timezone.now())
    return len(due)


def run_now(probe: Probe) -> checks.Outcome:
    """`POST /probes/{id}/run`: bir marta bajaradi va natijani qayd etadi (tasdiqlash qoidasi qo'llanadi)."""
    outcome = execute(probe)
    apply_outcome(probe, outcome, timezone.now())
    return outcome


def retired_ips() -> list[str]:
    """O'chirilgan IP lar (Q-12): domen shularga qarasa AL-063. `seed_registry` yozadi."""
    return [str(x) for x in Setting.get("retired_ips", [])]


def sync_dns_probe(domain: Domain) -> Probe | None:
    """Domenning DNS tekshiruvini kutilgan IP lar bilan moslab turadi (FR-DNS-001). Kutilgan IP yo'q bo'lsa
    solishtirish ma'nosiz: mavjud tekshiruv o'chiriladi, yangisi yaratilmaydi."""
    probe = Probe.objects.filter(domain=domain, type=Probe.Type.DNS).first()
    expected = [str(ip) for ip in domain.expected_ips]
    if not expected:
        if probe is not None and probe.enabled:
            Probe.objects.filter(pk=probe.pk).update(enabled=False, state=Probe.State.PAUSED)
        return None
    config = {
        "name": domain.fqdn,
        "rtype": "A",
        "resolvers": [*checks_net_resolvers(), "ns:auto"],
        "expected": expected,
        "retired_ips": retired_ips(),
    }
    if probe is None:
        return Probe.objects.create(
            project=domain.project,
            domain=domain,
            type=Probe.Type.DNS,
            name=f"{domain.fqdn} DNS",
            config=config,
            interval_s=300,
            timeout_s=10,
        )
    changed = probe.config.get("expected") != expected
    probe.config = {**probe.config, "expected": expected, "retired_ips": retired_ips()}
    probe.enabled = True
    if changed or probe.state == Probe.State.PAUSED:
        probe.state, probe.next_run_at = Probe.State.UNKNOWN, timezone.now()
        probe.consecutive_failures = 0
    probe.save()
    return probe


def checks_net_resolvers() -> list[str]:
    from .checks_net import PUBLIC_RESOLVERS

    return list(PUBLIC_RESOLVERS)


def ensure_domain_probes(domain: Domain) -> list[Probe]:
    """Domen qo'shilganda avtomatik tekshiruvlar (FR-REG-005): HTTP, TLS (tls_enabled), DNS (kutilgan IP bo'lsa).
    Qayta chaqirilsa takrorlamaydi."""
    created: list[Probe] = []
    if not Probe.objects.filter(domain=domain, type=Probe.Type.HTTP).exists():
        created.append(
            Probe.objects.create(
                project=domain.project, domain=domain, type=Probe.Type.HTTP, name=f"{domain.fqdn} HTTP",
                config={"url": f"https://{domain.fqdn}/", "expected_status": ["200-299"], "follow_redirects": True},
                interval_s=60, timeout_s=10,
            )
        )  # fmt: skip
    if domain.tls_enabled and not Probe.objects.filter(domain=domain, type=Probe.Type.TLS).exists():
        created.append(
            Probe.objects.create(
                project=domain.project, domain=domain, type=Probe.Type.TLS, name=f"{domain.fqdn} TLS",
                config={"host": domain.fqdn, "port": 443}, interval_s=6 * 3600, timeout_s=10,
            )
        )  # fmt: skip
    had_dns = Probe.objects.filter(domain=domain, type=Probe.Type.DNS).exists()
    if sync_dns_probe(domain) is not None and not had_dns:
        created.append(Probe.objects.get(domain=domain, type=Probe.Type.DNS))
    return created


# ----------------------------------------------------------------------- hisobotlar
def uptime(
    probe_id: str | UUID, windows: tuple[int, ...] = (1, 7, 30, 90), now: datetime | None = None
) -> dict[str, Any]:
    now = now or timezone.now()
    out: dict[str, Any] = {}
    with connection.cursor() as cursor:
        for days in windows:
            cursor.execute(
                "SELECT count(*), count(*) FILTER (WHERE ok) FROM probe_results WHERE probe_id = %s AND time >= %s",
                [probe_id, now - timedelta(days=days)],
            )
            total, ok = cursor.fetchone() or (0, 0)
            out[f"{days}d"] = {
                "checks": total,
                "uptime_percent": round(100 * ok / total, 3) if total else None,
            }
    return out


def recent_results(
    probe_id: str | UUID, start: datetime | None, end: datetime | None, limit: int
) -> list[dict[str, Any]]:
    sql = """
        SELECT time, ok, status_code, total_ms, dns_ms, connect_ms, tls_ms, ttfb_ms, error_kind, detail
        FROM probe_results WHERE probe_id = %s AND (%s::timestamptz IS NULL OR time >= %s) AND (%s::timestamptz IS NULL OR time <= %s)
        ORDER BY time DESC LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [probe_id, start, start, end, end, limit])
        cols = [c.name for c in cursor.description or []]
        rows = [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]
    for row in rows:  # Django psycopg `jsonb` ni matn sifatida qaytaradi (JSONField o'zi ochadi); xom SQL da o'zimiz ochamiz
        if isinstance(row.get("detail"), str):
            row["detail"] = json.loads(row["detail"])
    return rows
