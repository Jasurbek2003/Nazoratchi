import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from .health import readiness
from .http import error_response

logger = logging.getLogger(__name__)


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Sog'liq tekshiruvi (FR-SYS-005): baza javob bermasa 503. Redis tekshiruvi B1/B7 da."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("healthz: baza mavjud emas")
        return JsonResponse({"status": "unavailable", "db": "down"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    """Tayyorlik (FR-SYS-005): baza, Redis, bildirishnoma navbati, alert dvigateli. Birortasi nosoz bo'lsa 503."""
    checks = readiness()
    ready = all(c.ok for c in checks)
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {c.name: {"ok": c.ok, "detail": c.detail} for c in checks},
    }
    return JsonResponse(body, status=200 if ready else 503)


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    """404: API, ingest va agent yo'llari uchun yagona JSON xato formati (TZ 9.1.1); qolganlari oddiy matn."""
    if request.path.startswith(("/api/", "/ingest/", "/agent/")):
        return error_response("not_found", "Topilmadi.", 404)
    return HttpResponse("Topilmadi.", status=404, content_type="text/plain; charset=utf-8")


def server_error(request: HttpRequest) -> HttpResponse:
    """500: tafsilotsiz JSON (stek iz mijozga chiqmaydi, TZ 14)."""
    return error_response("internal_error", "Ichki xato.", 500)
