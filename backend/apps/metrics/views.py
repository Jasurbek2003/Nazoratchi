"""Prototip ko'rinishlari (F0). To'liq, autentifikatsiyali API B4 da; shu vaqtgacha faqat DEBUG da ochiq (/proto/api/...)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.core.http import error_response
from apps.registry.models import Server

from .models import Series
from .query import run_query

View = Callable[..., HttpResponse]


def debug_only(view: View) -> View:
    """PROTOTIP: autentifikatsiyasiz endpointlar prod'da yopiq (404)."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not settings.DEBUG:
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@require_GET
@debug_only
def proto_page(request: HttpRequest) -> HttpResponse:
    html = (Path(__file__).parent / "proto" / "index.html").read_text(encoding="utf-8")
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@require_GET
@debug_only
def servers(request: HttpRequest) -> JsonResponse:
    items = [
        {
            "id": str(s.id),
            "name": s.name,
            "status": s.status,
            "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
        }
        for s in Server.objects.order_by("name")
    ]
    return JsonResponse({"items": items})


@require_GET
@debug_only
def names(request: HttpRequest) -> HttpResponse:
    try:
        server_id = uuid.UUID(request.GET.get("server_id", ""))
    except ValueError:
        return error_response("validation_error", "server_id noto'g'ri.", 400)
    rows = Series.objects.filter(server_id=server_id).order_by("name", "id")
    return JsonResponse(
        {"items": [{"name": s.name, "labels": s.labels, "unit": s.unit} for s in rows]}
    )


@require_GET
@debug_only
def query(request: HttpRequest) -> HttpResponse:
    params = request.GET
    try:
        server_id = uuid.UUID(params.get("server_id", ""))
        name = params["name"]
        start, end = _parse_dt(params["from"]), _parse_dt(params["to"])
        max_points = int(params.get("max_points", "1000"))
    except (ValueError, KeyError):
        return error_response(
            "validation_error",
            "server_id, name, from, to (ISO) majburiy; max_points butun son.",
            400,
        )
    if not (100 <= max_points <= 2000) or start >= end:
        return error_response(
            "validation_error", "max_points 100–2000; from < to bo'lishi kerak.", 400
        )
    end = min(end, timezone.now())
    agg = params.get("agg", "avg")

    series_qs = Series.objects.filter(server_id=server_id, name=name)
    for key, value in params.items():
        if key.startswith("labels[") and key.endswith("]"):
            series_qs = series_qs.filter(labels__contains={key[7:-1]: value})

    out: list[dict[str, object]] = []
    source, step = "raw", 0
    try:
        for series in series_qs.order_by("id")[:50]:
            source, step, points = run_query(series.id, start, end, max_points, agg)
            out.append({"labels": series.labels, "points": points})
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    unit = series_qs.values_list("unit", flat=True).first() or ""
    return JsonResponse(
        {"name": name, "unit": unit, "step_seconds": step, "source": source, "series": out}
    )
