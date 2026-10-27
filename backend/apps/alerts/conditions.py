"""Qoida shartlarini hisoblash (TZ 12.3): threshold, absent, rate, forecast, state, and/or/not.

`evaluate_rule()` qoidani hozirgi ma'lumotda hisoblaydi va har obyekt (host, host × mount, job, kanal) uchun
`Subject` qaytaradi. `firing=None` — "ma'lumot yo'q": holat mashinasi o'zgarmaydi (agent jim bo'lganda
CPU alerti "tiklandi" bo'lib qolmasligi uchun; jimlikni AL-001/002 ushlaydi).
"""

import ipaddress
import json
import operator
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db import connection

from apps.heartbeats.models import HeartbeatJob
from apps.metrics.models import Series, SeriesLatest
from apps.notifications.models import Channel, Notification
from apps.probes.models import CertStatus, Probe
from apps.registry.models import Project, Server

MAX_DEPTH = 3
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
OPS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}
AGGREGATES = {"avg": "avg(value)", "min": "min(value)", "max": "max(value)"}
# Etiketlardan xabarda ko'rsatiladigani (host × mount -> 'main-2 (/)')
LABEL_DISPLAY = ("mount", "device", "iface", "container", "unit", "name", "service")
FANOUT_TYPES = {"threshold", "rate", "forecast"}
HOST_TYPES = FANOUT_TYPES | {"absent", "and", "or", "not"}
# state manbalari: manba -> {maydon: 'equals' turi}
STATE_SOURCES: dict[str, dict[str, type]] = {
    "reachability": {"tcp22": str},  # host (minimal tashqi tekshiruv; to'liq prober S4/S5)
    "heartbeat_job": {"overdue": bool, "failed": bool},
    "channel": {"failing": bool},
    "fleet": {"mass_silent": bool},
    "probe": {"state": str},  # S4: faol tekshiruv holati (cond.primary — ixtiyoriy filtr)
    "prober": {"stalled": bool},  # AL-085
    "cert": {"days_left_lte": int, "invalid": bool},  # S5: sertifikat (TLS tekshiruvi)
    "dns": {"mismatch": bool, "retired": bool},  # S5: DNS tekshiruvi
    # S6: loyiha zaxirasi (agent `backup_*` metrikalari + BackupRun tarixi); faqat expect_daily loyihalar
    "backup": {"age_hours_gt": int, "last_failed": bool, "size_small": bool, "size_large": bool},
    "self_backup": {
        "age_hours_gt": int,
        "failed": bool,
    },  # S7: Nazoratchi'ning o'z zaxirasi (FR-SYS-003)
}
FRESH_MIN_S = 120  # 'last' qiymati shundan eski bo'lsa "ma'lumot yo'q"
MIN_FORECAST_POINTS = 6
PROBE_CACHE_S = 20.0


class ConditionError(ValueError):
    """Qoida sharti sxemaga mos emas."""


@dataclass
class Subject:
    type: str  # host, job, channel, system
    id: str
    name: str
    scope_key: str
    firing: bool | None
    value: float | None = None
    detail: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    server_id: str | None = None


# ----------------------------------------------------------------------- tekshiruv (API uchun)
def _num(cond: dict[str, Any], key: str, lo: float, hi: float, *, required: bool = True) -> None:
    value = cond.get(key)
    if value is None:
        if required:
            raise ConditionError(f"{key} majburiy")
        return
    if isinstance(value, bool) or not isinstance(value, int | float) or not lo <= value <= hi:
        raise ConditionError(f"{key} {lo} dan {hi} gacha son bo'lishi kerak")


def _metric(cond: dict[str, Any], key: str = "metric") -> None:
    if not isinstance(cond.get(key), str) or not NAME_RE.match(cond[key]):
        raise ConditionError(f"{key} metrika nomi noto'g'ri")


def _labels(cond: dict[str, Any]) -> None:
    labels = cond.get("labels", {})
    if not isinstance(labels, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in labels.items()
    ):
        raise ConditionError("labels {matn: matn} bo'lishi kerak")


def validate_condition(cond: Any, depth: int = 0, *, nested: bool = False) -> None:
    if depth > MAX_DEPTH:
        raise ConditionError(f"ichma-ich chuqurlik {MAX_DEPTH} dan oshmasligi kerak")
    if not isinstance(cond, dict) or not isinstance(cond.get("type"), str):
        raise ConditionError("shart {'type': ...} obyekti bo'lishi kerak")
    kind = cond["type"]
    if (
        nested
        and kind not in HOST_TYPES
        and not (kind == "state" and cond.get("source") == "reachability")
    ):
        raise ConditionError(
            f"{kind} birlashtirishda ishlatilmaydi (faqat host darajasidagi shartlar)"
        )
    if kind == "threshold":
        _metric(cond)
        _labels(cond)
        if cond.get("op") not in OPS:
            raise ConditionError(f"op {', '.join(OPS)} dan biri bo'lishi kerak")
        _num(cond, "value", -1e15, 1e15)
        if cond.get("aggregate", "last") not in {*AGGREGATES, "last"}:
            raise ConditionError("aggregate avg, min, max yoki last bo'lishi kerak")
        _num(cond, "window_s", 1, 86400, required=False)
        if "when" in cond:
            when = cond["when"]
            if (
                not isinstance(when, dict)
                or set(when) != {"metric", "op", "value"}
                or when["op"] not in OPS
            ):
                raise ConditionError("when {metric, op, value} bo'lishi kerak")
            _metric(when)
            _num(when, "value", -1e15, 1e15)
    elif kind == "absent":
        _metric(cond)
        _num(cond, "max_age_s", 10, 86400)
    elif kind == "rate":
        _metric(cond)
        _labels(cond)
        _num(cond, "increase", 0, 1e15)
        _num(cond, "window_s", 10, 86400)
    elif kind == "forecast":
        _metric(cond)
        _metric(cond, "limit_metric")
        _labels(cond)
        _num(cond, "horizon_s", 60, 30 * 86400)
        _num(cond, "fit_window_s", 600, 7 * 86400)
        _num(cond, "min_r2", 0, 1, required=False)
        _num(cond, "min_used_percent", 0, 100, required=False)
    elif kind == "state":
        fields = STATE_SOURCES.get(cond.get("source", ""))
        if fields is None:
            raise ConditionError(f"source {', '.join(STATE_SOURCES)} dan biri bo'lishi kerak")
        expected = fields.get(cond.get("field", ""))
        if expected is None:
            raise ConditionError(f"field {', '.join(fields)} dan biri bo'lishi kerak")
        if "primary" in cond and not isinstance(cond["primary"], bool):
            raise ConditionError("primary true/false bo'lishi kerak")
        if expected is int and (
            isinstance(cond.get("equals"), bool) or not 0 <= cond.get("equals", -1) <= 3650
        ):
            raise ConditionError("equals 0..3650 oralig'idagi butun son bo'lishi kerak")
        if not isinstance(cond.get("equals"), expected) or (
            expected is str and cond["equals"] not in ("up", "down")
        ):
            raise ConditionError(
                "equals qiymati maydon turiga mos emas (reachability: 'up'|'down')"
            )
    elif kind in ("and", "or", "not"):
        operands = cond.get("of")
        size = (1, 1) if kind == "not" else (2, 5)
        if not isinstance(operands, list) or not size[0] <= len(operands) <= size[1]:
            raise ConditionError(
                f"{kind}: 'of' ro'yxati {size[0]}..{size[1]} elementli bo'lishi kerak"
            )
        for operand in operands:
            validate_condition(operand, depth + 1, nested=True)
    else:
        raise ConditionError(f"noma'lum shart turi: {kind}")


# ----------------------------------------------------------------------- tashqi tekshiruv (minimal)
_probe_cache: dict[tuple[str, int], tuple[float, bool]] = {}


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    """TCP ulanish. Natija 20 s keshlanadi. Loopback/link-local/multicast manzillar tekshirilmaydi
    (core o'z ichki xizmatlarini skanerlamasligi uchun); xususiy tarmoq manzillari ruxsat."""
    key = (host, port)
    hit = _probe_cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < PROBE_CACHE_S:
        return hit[1]
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            ok = True
    except (OSError, ValueError):
        ok = False
    _probe_cache[key] = (time.monotonic(), ok)
    return ok


# ----------------------------------------------------------------------- ma'lumotlarga kirish
class Ctx:
    """Bir hisoblash davri uchun ma'lumot keshi: har metrika bitta so'rov bilan o'qiladi."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self._servers: list[Server] | None = None
        self._series: dict[str, list[tuple[Series, SeriesLatest | None]]] = {}
        self._agg: dict[tuple[str, str, int], dict[int, float]] = {}
        self._inc: dict[tuple[str, int], dict[int, float]] = {}
        self._fan: dict[str, list[Subject]] = {}

    def servers(self) -> list[Server]:
        """Hech bo'lmaganda bir marta ma'lumot yuborgan, arxivlanmagan serverlar."""
        if self._servers is None:
            self._servers = list(
                Server.objects.exclude(status=Server.Status.ARCHIVED).filter(
                    last_seen_at__isnull=False
                )
            )
        return self._servers

    def series(
        self, metric: str, labels: dict[str, str] | None = None
    ) -> list[tuple[Series, SeriesLatest | None]]:
        if metric not in self._series:
            ids = {s.pk for s in self.servers()}
            rows = list(
                Series.objects.filter(name=metric, server_id__in=ids).select_related("server")
            )
            latest = {
                lt.series_id: lt
                for lt in SeriesLatest.objects.filter(series__in=[r.pk for r in rows])
            }
            self._series[metric] = [(r, latest.get(r.pk)) for r in rows]
        wanted = labels or {}
        return [
            (s, lt)
            for s, lt in self._series[metric]
            if all(s.labels.get(k) == v for k, v in wanted.items())
        ]

    def window_agg(self, metric: str, agg: str, window_s: int) -> dict[int, float]:
        key = (metric, agg, window_s)
        if key not in self._agg:
            sql = f"""
                SELECT series_id, {AGGREGATES[agg]}
                FROM metric_samples
                WHERE series_id IN (SELECT id FROM {Series._meta.db_table} WHERE name = %s)
                  AND time >= %s - %s * interval '1 second' AND time <= %s
                GROUP BY series_id
            """  # noqa: S608 (agg faqat oq ro'yxatdan, jadval nomi — model)
            with connection.cursor() as cursor:
                cursor.execute(sql, [metric, self.now, window_s, self.now])
                self._agg[key] = {
                    int(sid): float(v) for sid, v in cursor.fetchall() if v is not None
                }
        return self._agg[key]

    def increases(self, metric: str, window_s: int) -> dict[int, float]:
        """Counter o'sishi: musbat farqlar yig'indisi; qiymat kamaysa (qayta boshlash) yangi qiymat qo'shiladi."""
        key = (metric, window_s)
        if key not in self._inc:
            sql = f"""
                SELECT series_id, value FROM metric_samples
                WHERE series_id IN (SELECT id FROM {Series._meta.db_table} WHERE name = %s)
                  AND time >= %s - %s * interval '1 second' AND time <= %s
                ORDER BY series_id, time
            """  # noqa: S608 (jadval nomi — model)
            result: dict[int, float] = {}
            prev: dict[int, float] = {}
            with connection.cursor() as cursor:
                cursor.execute(sql, [metric, self.now, window_s, self.now])
                for sid, value in cursor.fetchall():
                    sid, value = int(sid), float(value)
                    if sid in prev:
                        delta = value - prev[sid]
                        result[sid] = result.get(sid, 0.0) + (delta if delta >= 0 else value)
                    prev[sid] = value
            self._inc[key] = result
        return self._inc[key]

    def points(
        self, series_id: int, window_s: int, bucket_s: int = 300
    ) -> list[tuple[float, float]]:
        sql = """
            SELECT extract(epoch FROM time_bucket(%s * interval '1 second', time)), avg(value)
            FROM metric_samples
            WHERE series_id = %s AND time >= %s - %s * interval '1 second' AND time <= %s
            GROUP BY 1 ORDER BY 1
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [bucket_s, series_id, self.now, window_s, self.now])
            return [(float(t), float(v)) for t, v in cursor.fetchall()]


def linear_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Eng kichik kvadratlar: (qiyalik birlik/soniya, R²)."""
    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mean_x) ** 2 for p in points)
    syy = sum((p[1] - mean_y) ** 2 for p in points)
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in points)
    if sxx == 0:
        return 0.0, 0.0
    slope = sxy / sxx
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0
    return slope, r2


# ----------------------------------------------------------------------- hisoblash
def _display(server: Server, labels: dict[str, str]) -> str:
    for key in LABEL_DISPLAY:
        if labels.get(key):
            return f"{server.name} ({labels[key]})"
    return server.name


def _host_subject(s: Series, firing: bool | None, value: float | None, detail: str) -> Subject:
    return Subject(
        "host", f"{s.server_id}:{s.labels_hash}", _display(s.server, s.labels), f"host:{s.server_id}",
        firing, value, detail, dict(s.labels), str(s.server_id),
    )  # fmt: skip


def _fresh(latest: SeriesLatest | None, ctx: Ctx, window_s: int) -> SeriesLatest | None:
    """Yangi qiymat yoki None ("ma'lumot yo'q": agent jim yoki seriya to'xtagan)."""
    if latest is None or (ctx.now - latest.time).total_seconds() > max(window_s, FRESH_MIN_S):
        return None
    return latest


def _threshold(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    metric, op, limit = cond["metric"], cond["op"], float(cond["value"])
    agg, window = cond.get("aggregate", "last"), int(cond.get("window_s", 60))
    aggs = None if agg == "last" else ctx.window_agg(metric, agg, window)
    when = cond.get("when")
    siblings: dict[tuple[Any, str], float] = {}
    if when:  # shart faqat o'sha seriyaning "hamroh" metrikasi shartni qanoatlantirsa qo'llanadi (masalan, kutilgan konteyner)
        siblings = {
            (s.server_id, s.labels_hash): lt.value
            for s, lt in ctx.series(when["metric"], cond.get("labels"))
            if _fresh(lt, ctx, 120) is not None
            and lt is not None
            and OPS[when["op"]](lt.value, float(when["value"]))
        }
    out = []
    for s, raw_latest in ctx.series(metric, cond.get("labels")):
        if when and (s.server_id, s.labels_hash) not in siblings:
            out.append(_host_subject(s, False, None, f"{when['metric']} sharti bajarilmagan"))
            continue
        latest = _fresh(raw_latest, ctx, window)
        if latest is None:
            out.append(_host_subject(s, None, None, f"{metric}: yangi ma'lumot yo'q"))
            continue
        value = latest.value if aggs is None else aggs.get(s.pk)
        if value is None:
            out.append(_host_subject(s, None, None, f"{metric}: oynada ma'lumot yo'q"))
            continue
        out.append(
            _host_subject(
                s, OPS[op](value, limit), value, f"{metric} = {value:.1f} (chegara {op} {limit:g})"
            )
        )
    return out


def _rate(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    metric, limit, window = cond["metric"], float(cond["increase"]), int(cond["window_s"])
    inc = ctx.increases(metric, window)
    out = []
    for s, _latest in ctx.series(metric, cond.get("labels")):
        value = inc.get(s.pk, 0.0)
        out.append(
            _host_subject(
                s,
                value > limit,
                value,
                f"{metric}: {window // 60} daqiqada +{value:g} (chegara > {limit:g})",
            )
        )
    return out


def _forecast(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    metric, limit_metric = cond["metric"], cond["limit_metric"]
    horizon, fit = int(cond["horizon_s"]), int(cond["fit_window_s"])
    min_r2, min_pct = float(cond.get("min_r2", 0.5)), float(cond.get("min_used_percent", 0))
    totals = {
        (s.server_id, s.labels_hash): lt for s, lt in ctx.series(limit_metric, cond.get("labels"))
    }
    out = []
    for s, raw_latest in ctx.series(metric, cond.get("labels")):
        total = totals.get((s.server_id, s.labels_hash))
        latest = _fresh(raw_latest, ctx, 120)
        if latest is None or total is None or total.value <= 0:
            out.append(_host_subject(s, None, None, f"{metric}: bashorat uchun ma'lumot yo'q"))
            continue
        points = ctx.points(s.pk, fit)
        if len(points) < MIN_FORECAST_POINTS:
            out.append(
                _host_subject(s, None, None, f"{metric}: bashorat uchun ma'lumot yetarli emas")
            )
            continue
        slope, r2 = linear_fit(points)
        used_pct = 100 * latest.value / total.value
        if used_pct < min_pct or r2 < min_r2 or slope <= 0:
            out.append(
                _host_subject(
                    s, False, None, f"{used_pct:.0f}% band, o'sish ishonchli emas (R²={r2:.2f})"
                )
            )
            continue
        eta = (total.value - latest.value) / slope
        out.append(
            _host_subject(
                s,
                eta <= horizon,
                eta,
                f"{used_pct:.0f}% band, to'lishiga ≈ {_human(eta)} (R²={r2:.2f})",
            )
        )
    return out


def _human(seconds: float) -> str:
    if seconds >= 86400:
        return f"{seconds / 86400:.1f} kun"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} soat"
    return f"{max(seconds, 0) / 60:.0f} daqiqa"


def _fanout(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    key = json.dumps(cond, sort_keys=True)
    if key not in ctx._fan:
        ctx._fan[key] = {"threshold": _threshold, "rate": _rate, "forecast": _forecast}[
            cond["type"]
        ](cond, ctx)
    return ctx._fan[key]


Result = tuple[bool | None, float | None, str]


def last_heard(server: Server, ctx: Ctx, metric: str = "agent_up") -> datetime | None:
    """Serverdan eng oxirgi ma'lumot vaqti: `metric` ning oxirgi namunasi, bo'lmasa `last_seen_at`."""
    times = [lt.time for s, lt in ctx.series(metric) if s.server_id == server.pk and lt]
    return max(times) if times else server.last_seen_at


def _absent(cond: dict[str, Any], server: Server, ctx: Ctx) -> Result:
    last = last_heard(server, ctx, cond["metric"])
    if last is None:
        return None, None, "ma'lumot hech qachon kelmagan"
    age = (ctx.now - last).total_seconds()
    return (
        age > cond["max_age_s"],
        age,
        f"aloqa yo'q: {_human(age)} (oxirgi ma'lumot {last:%H:%M:%S} UTC)",
    )


def _reachability(cond: dict[str, Any], server: Server) -> Result:
    if not server.public_ipv4:
        return None, None, "IP manzil kiritilmagan"
    up = tcp_probe(str(server.public_ipv4), 22)
    return (
        ("up" if up else "down") == cond["equals"],
        None,
        f"TCP:22 {'javob beradi' if up else 'javob yo`q'}",
    )


def _host_eval(cond: dict[str, Any], server: Server, ctx: Ctx) -> Result:
    kind = cond["type"]
    if kind == "absent":
        return _absent(cond, server, ctx)
    if kind == "state":
        return _reachability(cond, server)
    if kind in FANOUT_TYPES:
        mine = [s for s in _fanout(cond, ctx) if s.server_id == str(server.pk)]
        known = [s for s in mine if s.firing is not None]
        if any(s.firing for s in known):
            worst = next(s for s in known if s.firing)
            return True, worst.value, worst.detail
        return (False if known else None), None, mine[0].detail if mine else "ma'lumot yo'q"
    parts: list[Result] = []
    for operand in cond["of"]:
        res = _host_eval(operand, server, ctx)
        parts.append(res)
        if kind == "and" and res[0] is False:
            break  # qisqa tutashuv: keyingi (qimmat) tekshiruvlar kerak emas
        if kind == "or" and res[0] is True:
            break
    flags = [p[0] for p in parts]
    detail = "; ".join(p[2] for p in parts if p[2])
    if kind == "not":
        return (None if flags[0] is None else not flags[0]), None, detail
    if kind == "and":
        if False in flags:
            return False, None, detail
        return (None if None in flags else True), None, detail
    if True in flags:
        return True, None, detail
    return (None if None in flags else False), None, detail


def _per_host(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    out = []
    for server in ctx.servers():
        firing, value, detail = _host_eval(cond, server, ctx)
        out.append(
            Subject(
                "host",
                str(server.pk),
                server.name,
                f"host:{server.pk}",
                firing,
                value,
                detail,
                {},
                str(server.pk),
            )
        )
    return out


def _state_other(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    source, fld = cond["source"], cond["field"]
    out: list[Subject] = []
    if source == "heartbeat_job":
        for job in HeartbeatJob.objects.filter(enabled=True):
            if fld == "overdue":
                if job.last_beat_at is None:
                    firing, detail = None, "hali bir marta ham xabar bermagan"
                else:
                    late = (ctx.now - job.last_beat_at).total_seconds()
                    firing = late > job.expected_every_s + job.grace_s
                    detail = f"oxirgi xabar {_human(late)} oldin (kutilgan: har {_human(job.expected_every_s)} + {_human(job.grace_s)})"
            else:
                firing = None if job.last_ok is None else not job.last_ok
                detail = f"oxirgi xabar: {job.last_message or 'xato'}"
            out.append(Subject("job", str(job.pk), job.name, f"job:{job.pk}", firing, None, detail))
    elif source == "channel":
        for ch in Channel.objects.filter(enabled=True):
            recent = list(
                Notification.objects.filter(channel=ch).exclude(status="queued").order_by("-id")[:3]
            )
            failing = len(recent) == 3 and all(n.status == "failed" for n in recent)
            detail = (
                f"oxirgi 3 yuborish muvaffaqiyatsiz: {ch.last_error}" if failing else "ishlayapti"
            )
            out.append(
                Subject("channel", str(ch.pk), ch.name, f"channel:{ch.pk}", failing, None, detail)
            )
    elif source == "probe":
        out.extend(_state_probes(cond, ctx))
    elif source == "prober":
        out.append(_prober_stalled(ctx))
    elif source == "cert":
        out.extend(_state_certs(cond, ctx))
    elif source == "dns":
        out.extend(_state_dns(cond, ctx))
    elif source == "backup":
        out.extend(_state_backups(cond, ctx))
    elif source == "self_backup":
        out.append(_state_self_backup(cond, ctx))
    else:  # fleet
        servers = [s for s in ctx.servers() if s.status != Server.Status.PAUSED]
        silent = [
            s for s in servers if (t := last_heard(s, ctx)) and (ctx.now - t).total_seconds() > 120
        ]
        firing = len(servers) >= 2 and len(silent) / len(servers) >= 0.5
        names = ", ".join(sorted(s.name for s in silent)[:10])
        out.append(
            Subject(
                "system",
                "fleet",
                "Nazoratchi",
                "system",
                firing,
                float(len(silent)),
                f"{len(silent)}/{len(servers)} host jim: {names}",
            )
        )
    return out


PROBER_STALL_S = 180


def _state_self_backup(cond: dict[str, Any], ctx: Ctx) -> Subject:
    from apps.backups.models import SelfBackup

    name = "Nazoratchi o'z zaxirasi"
    latest = SelfBackup.objects.order_by("-created_at").first()
    last_ok = SelfBackup.objects.filter(status=SelfBackup.Status.OK).order_by("-created_at").first()
    firing: bool | None
    if cond["field"] == "failed":
        firing = None if latest is None else latest.status == SelfBackup.Status.FAILED
        detail = (
            f"oxirgi urinish muvaffaqiyatsiz: {latest.error}"
            if firing and latest
            else "oxirgi urinish muvaffaqiyatli"
        )
    elif last_ok is None:
        firing, detail = (
            None,
            "o'z zaxirasi hali bir marta ham yuborilmagan (yoqilmagan bo'lishi mumkin)",
        )
    else:
        hours = (ctx.now - last_ok.created_at).total_seconds() / 3600
        firing = hours > cond["equals"]
        detail = f"oxirgi muvaffaqiyatli o'z zaxirasi {hours:.0f} soat oldin (chegara {cond['equals']} soat)"
    return Subject("system", "self_backup", name, "system", firing, None, detail)


def _state_backups(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    """Loyiha zaxirasi (FR-BKP-002/004/005). Faqat faol, ko'chirilgan va `backup.expect_daily` loyihalar.
    Agent jim bo'lsa (metrikalar 15 daqiqadan eski) — noma'lum: jimlikni AL-001/002 ushlaydi."""
    from apps.backups import services as bk
    from apps.registry.models import ProjectServer

    out = []
    projects = [
        p
        for p in Project.objects.filter(status=Project.Status.ACTIVE, moved=True)
        if (p.backup or {}).get("expect_daily")
    ]
    data = bk.collect(ctx.now, {p.slug for p in projects})
    links: dict[Any, list[Any]] = {}
    for link in ProjectServer.objects.filter(project__in=projects, environment="production"):
        links.setdefault(link.project_id, []).append(link.server_id)
    for project in projects:
        servers = links.get(project.pk, [])
        if not servers:
            continue  # zaxira qaysi serverda turishi noma'lum
        pbs = [data[(sid, project.slug)] for sid in servers if (sid, project.slug) in data]
        pb = max(pbs, key=lambda x: x.seen_at or ctx.now) if pbs else None
        field = cond["field"]
        project_hours = (ctx.now - project.created_at).total_seconds() / 3600
        firing: bool | None
        detail = ""
        value: float | None = None
        if field == "age_hours_gt":
            limit = cond["equals"]
            if pb is None or pb.last_success_ts is None:
                firing = True if project_hours > limit else None
                detail = (
                    "zaxira hech qachon olinmagan (agent ma'lumot bermagan)"
                    if firing
                    else "hali zaxira kutilmoqda"
                )
            elif not bk.agent_alive(pb, ctx.now):
                firing, detail = None, "agent jim: zaxira holati noma'lum"
            else:
                value = (ctx.now.timestamp() - pb.last_success_ts) / 3600
                firing = value > limit
                detail = (
                    f"oxirgi muvaffaqiyatli zaxira {value:.0f} soat oldin (chegara {limit} soat)"
                )
        elif field == "last_failed":
            if pb is None or pb.last_status is None or not bk.agent_alive(pb, ctx.now):
                firing, detail = None, "ma'lumot yo'q"
            else:
                firing = pb.last_status < 1
                detail = (
                    "oxirgi zaxira muvaffaqiyatsiz tugadi (appctl state.json)"
                    if firing
                    else "oxirgi zaxira muvaffaqiyatli"
                )
        else:  # size_small | size_large
            check = bk.size_check(servers[0] if pb is None else pb.server_id, project.slug)
            if check is None or (ctx.now - check.finished_at).total_seconds() > 72 * 3600:
                firing, detail = None, "hajm tahlili uchun tarix yetarli emas (< 8 zaxira)"
            else:
                small = field == "size_small"
                firing = check.ratio < bk.SMALL_RATIO if small else check.ratio > bk.LARGE_RATIO
                value = check.ratio
                detail = f"hajm {check.latest / 1e6:.1f} MB, oldingi 7 ta medianasi {check.median / 1e6:.1f} MB ({check.ratio:.2f}x)"
        labels = _project_labels(project, "")
        out.append(
            Subject(
                "backup",
                project.slug,
                project.slug,
                f"project:{project.pk}",
                firing,
                value,
                detail,
                labels,
            )
        )
    return out


CERT_STALE_S = (
    2 * 86400
)  # sertifikat holati shundan eski bo'lsa "ma'lumot yo'q" (tekshiruv to'xtagan)


def _active_project(project: Project | None) -> bool:
    """Ko'chirilmagan (FR-REG-007) va arxivlangan (FR-REG-006) loyiha tekshiruvlari alert bermaydi."""
    return project is None or (project.moved and project.status == Project.Status.ACTIVE)


def _project_labels(project: Project | None, domain: str) -> dict[str, str]:
    return {
        "project_id": str(project.pk) if project else "",
        "project": project.name if project else "",
        "domain": domain,
    }


def _state_certs(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    out = []
    for cs in CertStatus.objects.filter(source=CertStatus.Source.PROBE).select_related(
        "domain__project"
    ):
        domain = cs.domain
        if domain is not None and (
            domain.status != "active" or not _active_project(domain.project)
        ):
            continue
        project = domain.project if domain else None
        days_left = int((cs.not_after - ctx.now).total_seconds() // 86400)
        if (ctx.now - cs.checked_at).total_seconds() > CERT_STALE_S:
            firing, detail = None, "sertifikat holati eskirgan (tekshiruv ishlamayapti)"
        elif cond["field"] == "days_left_lte":
            firing = days_left <= cond["equals"]
            detail = (
                f"{cs.name}: {days_left} kun qoldi (tugash {cs.not_after:%Y-%m-%d} UTC)"
                if days_left >= 0
                else f"{cs.name}: muddati {-days_left} kun oldin tugagan!"
            )
        else:  # invalid
            problems = [
                x
                for x, ok in (
                    ("zanjir to'liq emas", cs.chain_ok),
                    ("nom SAN ga mos emas", cs.hostname_ok),
                )
                if ok is False
            ]
            firing = bool(problems)
            detail = f"{cs.name}: {', '.join(problems)}" if problems else f"{cs.name}: yaroqli"
        scope_key = f"project:{project.pk}" if project else f"cert:{cs.pk}"
        out.append(
            Subject(
                "cert",
                str(cs.pk),
                cs.name,
                scope_key,
                firing,
                float(days_left),
                detail,
                _project_labels(project, cs.name),
            )
        )
    return out


def _state_dns(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    from apps.probes.services import recent_results

    out = []
    for probe in Probe.objects.filter(enabled=True, type="dns").select_related("project", "domain"):
        project: Project | None = probe.project
        if not _active_project(project):
            continue
        last = recent_results(probe.pk, None, None, 1)
        detail_json = (last[0]["detail"] or {}) if last else {}
        if cond["field"] == "retired":
            firing = bool(detail_json.get("retired")) if last else None
            detail = (
                f"eski (o'chirilgan) IP ga qaraydi: {', '.join(detail_json.get('retired', []))}"
                if firing
                else "eski IP yo'q"
            )
        else:  # mismatch: 3 marta tasdiqlangan (down) VA mismatch_after_min davomida
            if probe.state in (Probe.State.UNKNOWN, Probe.State.PAUSED):
                firing, detail = None, "hali tasdiqlanmagan"
            else:
                wait = int(probe.config.get("mismatch_after_min", 10)) * 60
                held = (ctx.now - probe.state_since).total_seconds() if probe.state_since else 0
                firing = probe.state == Probe.State.DOWN and held >= wait
                bad = [
                    f"{r['resolver']} -> {','.join(r['answers']) or r['rcode']}"
                    for r in detail_json.get("resolvers", [])
                    if not r["matches"]
                ]
                kutilgan = ", ".join(probe.config.get("expected", []))
                detail = f"kutilgan {kutilgan}; mos emas: {'; '.join(bad)}" if bad else "mos"
        domain = probe.domain.fqdn if probe.domain else probe.config.get("name", "")
        scope_key = f"project:{project.pk}" if project else f"probe:{probe.pk}"
        out.append(
            Subject(
                "probe",
                str(probe.pk),
                probe.name,
                scope_key,
                firing,
                None,
                detail,
                _project_labels(project, domain),
            )
        )
    return out


def _last_error(probe: Probe) -> str:
    from apps.probes.services import recent_results

    rows = recent_results(probe.pk, None, None, 1)
    if not rows or rows[0]["ok"]:
        return ""
    row = rows[0]
    status = f"HTTP {row['status_code']}, " if row["status_code"] else ""
    return f"{status}{row['error_kind'] or 'xato'}"


def _state_probes(cond: dict[str, Any], ctx: Ctx) -> list[Subject]:
    """Faol tekshiruv `down`/`up` holati. Ko'chirilmagan (moved=false) yoki arxivlangan loyiha tekshiruvlari
    hisoblanmaydi (FR-REG-006/007). Incident qamrovi — loyiha (yo'q bo'lsa tekshiruvning o'zi)."""
    primary = cond.get("primary")
    out = []
    probes = Probe.objects.filter(enabled=True, type__in=["http", "tcp"]).select_related(
        "project", "domain"
    )
    for probe in probes:
        project: Project | None = probe.project
        if project is not None and (not project.moved or project.status != Project.Status.ACTIVE):
            continue
        is_primary = bool(probe.config.get("primary"))
        if primary is not None and is_primary != primary:
            continue
        if probe.state in (Probe.State.UNKNOWN, Probe.State.PAUSED):
            firing = None
            detail = "hali tasdiqlanmagan"
        else:
            firing = probe.state == cond["equals"]
            since = (
                f"{_human((ctx.now - probe.state_since).total_seconds())} dan beri"
                if probe.state_since
                else ""
            )
            detail = " ".join(
                x
                for x in (_last_error(probe) if probe.state == Probe.State.DOWN else "", since)
                if x
            )
        labels = {
            "project_id": str(project.pk) if project else "",
            "project": project.name if project else "",
        }
        if probe.domain is not None:
            labels["domain"] = probe.domain.fqdn
        scope_key = f"project:{project.pk}" if project else f"probe:{probe.pk}"
        out.append(
            Subject("probe", str(probe.pk), probe.name, scope_key, firing, None, detail, labels)
        )
    return out


def _prober_stalled(ctx: Ctx) -> Subject:
    probes = list(Probe.objects.filter(enabled=True))
    if not probes:
        return Subject("system", "prober", "Prober", "system", False, None, "faol tekshiruv yo'q")
    ran = [p.last_run_at for p in probes if p.last_run_at]
    if ran:
        age = (ctx.now - max(ran)).total_seconds()
        return Subject(
            "system",
            "prober",
            "Prober",
            "system",
            age > PROBER_STALL_S,
            age,
            f"hech bir tekshiruv {_human(age)} bajarilmadi",
        )
    oldest = min(p.created_at for p in probes)
    waited = (ctx.now - oldest).total_seconds()
    return Subject(
        "system",
        "prober",
        "Prober",
        "system",
        True if waited > PROBER_STALL_S else None,
        waited,
        "tekshiruvlar hali bir marta ham bajarilmagan",
    )


def evaluate_rule(rule: Any, ctx: Ctx) -> list[Subject]:
    """Qoida shartini hozirgi ma'lumotda hisoblaydi (holatni o'zgartirmaydi)."""
    cond = rule.condition
    kind = cond["type"]
    if kind in FANOUT_TYPES:
        subjects = list(_fanout(cond, ctx))
    elif kind == "state" and cond["source"] != "reachability":
        subjects = _state_other(cond, ctx)
    else:
        subjects = _per_host(cond, ctx)
    scope = rule.scope or {}
    allowed: set[str] | None = None
    if scope.get("ids"):
        allowed = {str(i) for i in scope["ids"]}
    if scope.get("tags"):
        tagged = {str(s.pk) for s in ctx.servers() if set(s.tags) & set(scope["tags"])}
        allowed = tagged if allowed is None else allowed & tagged
    if allowed is not None:
        subjects = [s for s in subjects if s.server_id is None or s.server_id in allowed]
    return subjects
