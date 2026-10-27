import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from .health import readiness

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
