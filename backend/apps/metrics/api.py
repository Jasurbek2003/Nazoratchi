"""Metrikalar so'rovi API (TZ 9.5, B4): `query`, `latest`, `names`, `top` + server konteynerlari va fayl tizimlari
(TZ 9.3). Hammasi autentifikatsiyadan o'tgan foydalanuvchi uchun (GET)."""

import math
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.http import error_response
from apps.registry.models import Server

from .models import Series, SeriesLatest
from .query import run_query

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
MAX_SERIES = 50
MAX_SPAN = timedelta(days=400)
FRESH = timedelta(minutes=5)  # `top` va `containers` uchun "yangi" qiymat chegarasi


def _dt(value: str) -> datetime:
    parsed = parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        raise ValueError("ISO-8601 va vaqt zonasi (masalan, ...Z) kerak")
    return parsed


def _server(value: str | UUID | None) -> Server | None:
    try:
        return Server.objects.filter(pk=UUID(str(value or ""))).first()
    except ValueError:
        return None


MIN_GAP_S = (
    120  # agent oralig'i 15-30 s: 2 daqiqadan kam uzilish "bo'shliq" emas, oddiy namuna oralig'i
)


def fill_gaps(points: list[list[float]], step_s: int) -> list[list[float | None]]:
    """Ma'lumot bo'lmagan oraliqlar `null` bilan (grafikda uzilish): qo'shni nuqtalar orasi
    `max(3 qadam, 2 daqiqa)` dan uzoq bo'lsa. Chegara so'rov qadamiga emas, namuna oralig'iga bog'liq."""
    out: list[list[float | None]] = []
    gap_ms = max(step_s * 3, MIN_GAP_S) * 1000
    for point in points:
        if out and point[0] - float(out[-1][0] or 0) > gap_ms:
            out.append([float(out[-1][0] or 0) + step_s * 1000, None])
        out.append([point[0], point[1]])
    return out


class MetricsQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        q = request.query_params
        server = _server(q.get("server_id"))
        name = q.get("name", "")
        if server is None or not NAME_RE.match(name):
            return error_response(
                "validation_error", "server_id (mavjud server) va name majburiy.", 400
            )
        try:
            start, end = _dt(q["from"]), _dt(q["to"])
            max_points = int(q.get("max_points", "1000"))
            step = int(q["step"]) if "step" in q else None
        except (KeyError, ValueError):
            return error_response(
                "validation_error",
                "from, to (ISO, zona bilan) majburiy; max_points va step butun son.",
                400,
            )
        now = timezone.now()
        if end > now + timedelta(minutes=1):
            return error_response("validation_error", "to kelajakda bo'lmasligi kerak.", 400)
        end = min(end, now)
        if start >= end or end - start > MAX_SPAN:
            return error_response(
                "validation_error", "from < to va oraliq ≤ 400 kun bo'lishi kerak.", 400
            )
        if step is not None:
            if step < 1:
                return error_response("validation_error", "step musbat bo'lishi kerak.", 400)
            max_points = math.ceil((end - start).total_seconds() / step)
        if not 1 <= max_points <= 2000 or (step is None and not 100 <= max_points <= 2000):
            return error_response(
                "validation_error", "max_points 100–2000 (yoki step bilan ≤ 2000 nuqta).", 400
            )
        agg = q.get("agg", "avg")
        if agg not in ("avg", "min", "max", "last"):
            return error_response(
                "validation_error", "agg avg, min, max yoki last bo'lishi kerak.", 400
            )
        series_qs = Series.objects.filter(server=server, name=name)
        for key, value in q.items():
            if key.startswith("labels[") and key.endswith("]"):
                series_qs = series_qs.filter(labels__contains={key[7:-1]: value})
        out: list[dict[str, Any]] = []
        source, used_step = "raw", 0
        try:
            for series in series_qs.order_by("id")[:MAX_SERIES]:
                source, used_step, points = run_query(series.pk, start, end, max_points, agg)
                out.append({"labels": series.labels, "points": fill_gaps(points, used_step)})
        except ValueError as exc:
            return error_response("validation_error", str(exc), 400)
        unit = series_qs.values_list("unit", flat=True).first() or ""
        return Response(
            {"name": name, "unit": unit, "step_seconds": used_step, "source": source, "series": out}
        )


class MetricsLatestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        q = request.query_params
        server = _server(q.get("server_id"))
        names = [n for n in q.get("names", "").split(",") if n]
        if (
            server is None
            or not names
            or len(names) > 50
            or not all(NAME_RE.match(n) for n in names)
        ):
            return error_response(
                "validation_error", "server_id va names (vergul bilan, ≤ 50) majburiy.", 400
            )
        rows = SeriesLatest.objects.filter(
            series__server=server, series__name__in=names
        ).select_related("series")
        items: dict[str, list[dict[str, Any]]] = {n: [] for n in names}
        for row in rows.order_by("series__name", "series__labels_hash"):
            items[row.series.name].append(
                {"labels": row.series.labels, "time": row.time, "value": row.value}
            )
        return Response({"server_id": str(server.pk), "metrics": items})


class MetricsNamesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        rows = Series.objects.all()
        if sid := request.query_params.get("server_id"):
            server = _server(sid)
            if server is None:
                return error_response("validation_error", "server_id noto'g'ri.", 400)
            rows = rows.filter(server=server)
        grouped = rows.values("name", "unit", "kind").annotate(series=Count("id")).order_by("name")
        label_keys: dict[str, set[str]] = {}
        for labels, name in rows.values_list("labels", "name").distinct()[:5000]:
            label_keys.setdefault(name, set()).update(labels)
        items = [{**g, "label_keys": sorted(label_keys.get(g["name"], set()))} for g in grouped]
        return Response({"items": items})


class MetricsTopView(APIView):
    """Eng yuklangan seriyalar (server, konteyner, fayl tizimi): oxirgi 5 daqiqadagi qiymat bo'yicha kamayish tartibida."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        q = request.query_params
        metric = q.get("metric", "cpu_busy_percent")
        limit = q.get("limit", "5")
        if not NAME_RE.match(metric) or not limit.isdigit() or not 1 <= int(limit) <= 50:
            return error_response(
                "validation_error", "metric (metrika nomi) va limit (1–50) kerak.", 400
            )
        cutoff = timezone.now() - FRESH
        rows = (
            SeriesLatest.objects.filter(series__name=metric, time__gte=cutoff)
            .exclude(series__server__status=Server.Status.ARCHIVED)
            .select_related("series__server")
            .order_by("-value")[: int(limit)]
        )
        items = [
            {
                "server_id": str(r.series.server_id),
                "server": r.series.server.name,
                "labels": r.series.labels,
                "value": r.value,
                "time": r.time,
            }
            for r in rows
        ]
        return Response({"metric": metric, "items": items})


# ----------------------------------------------------------------------- server sahifasi uchun
class ServerContainersView(APIView):
    """`GET /servers/{id}/containers`: konteynerlar va oxirgi qiymatlari (FR-DKR-001). Yo'qolib ketgan (5 daqiqadan
    eski) konteynerlar `stale: true` bilan qaytadi."""

    permission_classes = [IsAuthenticated]
    FIELDS = {
        "docker_container_running": "running", "docker_container_restarts_total": "restarts",
        "docker_container_uptime_seconds": "uptime_seconds", "docker_container_health": "health",
        "docker_container_oom_killed": "oom_killed", "docker_container_expected": "expected",
    }  # fmt: skip

    def get(self, request: Request, pk: str) -> HttpResponse:
        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        rows = SeriesLatest.objects.filter(
            series__server=server, series__name__in=self.FIELDS
        ).select_related("series")
        now = timezone.now()
        containers: dict[str, dict[str, Any]] = {}
        for row in rows:
            labels = row.series.labels
            c = containers.setdefault(
                labels.get("container", ""),
                {
                    "container": labels.get("container", ""),
                    "project": labels.get("project", ""),
                    "service": labels.get("service", ""),
                    "time": row.time,
                },
            )
            c[self.FIELDS[row.series.name]] = row.value
            c["time"] = max(c["time"], row.time)
        for c in containers.values():
            c["running"] = bool(c.get("running"))
            c["stale"] = now - c["time"] > FRESH
        return Response({"items": sorted(containers.values(), key=lambda c: c["container"])})


class ServerFilesystemsView(APIView):
    """`GET /servers/{id}/filesystems`: fayl tizimlari, bandlik va to'lishga qolgan vaqt bashorati (6.7.4)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> HttpResponse:
        from apps.alerts.conditions import MIN_FORECAST_POINTS, Ctx, linear_fit

        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        names = [
            "fs_total_bytes",
            "fs_used_bytes",
            "fs_avail_bytes",
            "fs_used_percent",
            "fs_readonly",
        ]
        latest = SeriesLatest.objects.filter(
            series__server=server, series__name__in=names
        ).select_related("series")
        mounts: dict[str, dict[str, Any]] = {}
        series_ids: dict[str, int] = {}
        for row in latest:
            mount = row.series.labels.get("mount", "")
            m = mounts.setdefault(
                mount,
                {
                    "mount": mount,
                    "device": row.series.labels.get("device", ""),
                    "fstype": row.series.labels.get("fstype", ""),
                    "time": row.time,
                },
            )
            m[row.series.name.removeprefix("fs_")] = row.value
            m["time"] = max(m["time"], row.time)
            if row.series.name == "fs_used_bytes":
                series_ids[mount] = row.series.pk
        ctx = Ctx(timezone.now())
        for mount, m in mounts.items():
            m["readonly"] = bool(m.pop("readonly", 0))
            m["days_until_full"] = None
            if mount in series_ids and m.get("total_bytes"):
                points = ctx.points(series_ids[mount], 6 * 3600)
                if len(points) >= MIN_FORECAST_POINTS:
                    slope, r2 = linear_fit(points)
                    if slope > 0 and r2 >= 0.5:
                        m["days_until_full"] = round(
                            (m["total_bytes"] - m["used_bytes"]) / slope / 86400, 1
                        )
        return Response({"items": sorted(mounts.values(), key=lambda m: m["mount"])})
