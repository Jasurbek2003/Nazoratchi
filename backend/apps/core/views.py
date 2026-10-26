import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

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
