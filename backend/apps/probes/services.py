"""Tekshiruvlarni rejalash, bajarish va holatini yuritish (TZ 6.8).

Tasdiqlash qoidasi: muvaffaqiyatsiz natijadan keyin 15 s oraliq bilan qayta tekshiriladi; 3 ketma-ket xato = `down`;
bitta muvaffaqiyat = `up`. Qayta tekshiruv oqim ichida uxlamaydi: `next_run_at` 15 s ga suriladi.
"""

import ipaddress
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from apps.registry.models import Domain

from . import checks
from .models import Probe

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
    else:
        raise ProbeConfigError(f"{kind} turi hali qo'llab-quvvatlanmaydi (tls, dns, whois — S5)")


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
    import json

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


def ensure_domain_probes(domain: Domain) -> list[Probe]:
    """Domen qo'shilganda avtomatik HTTP tekshiruv (FR-REG-005). TLS/DNS — S5. Qayta chaqirilsa takrorlamaydi."""
    created: list[Probe] = []
    if not Probe.objects.filter(domain=domain, type=Probe.Type.HTTP).exists():
        created.append(
            Probe.objects.create(
                project=domain.project,
                domain=domain,
                type=Probe.Type.HTTP,
                name=f"{domain.fqdn} HTTP",
                config={
                    "url": f"https://{domain.fqdn}/",
                    "expected_status": ["200-299"],
                    "follow_redirects": True,
                },
                interval_s=60,
                timeout_s=10,
            )
        )
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
        return [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]
