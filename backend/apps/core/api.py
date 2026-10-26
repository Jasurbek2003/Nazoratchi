"""DRF: yagona xato formati (TZ 9.1.1). RBAC — apps.core.permissions."""

import json
from typing import Any

from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .http import error_response


def _details(detail: Any) -> list[dict[str, str]]:
    """DRF `ValidationError.detail` ni TZ ning `details` ro'yxatiga aylantiradi."""
    out: list[dict[str, str]] = []
    if isinstance(detail, dict):
        for field, value in detail.items():
            items = value if isinstance(value, list) else [value]
            for item in items:
                code = getattr(item, "code", "invalid")
                out.append({"field": str(field), "code": str(code), "message": str(item)})
    elif isinstance(detail, list):
        for item in detail:
            out.append({"field": "non_field_errors", "code": "invalid", "message": str(item)})
    return out


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        return None  # kutilmagan xato: Django 500 beradi va logga yozadi
    code, message = "internal_error", "Kutilmagan xato."
    details: list[dict[str, str]] | None = None
    status = response.status_code
    if isinstance(exc, exceptions.ValidationError):
        code, message, details = (
            "validation_error",
            "Ma'lumot noto'g'ri kiritilgan.",
            _details(exc.detail),
        )
    elif isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        status = 401
        code, message = "unauthenticated", "Avval tizimga kiring."
    elif isinstance(exc, exceptions.PermissionDenied):
        code = "csrf_failed" if "CSRF" in str(exc.detail) else "forbidden"
        message = "Ruxsat yo'q." if code == "forbidden" else "CSRF tekshiruvi o'tmadi."
    elif isinstance(exc, exceptions.NotFound | Http404):
        code, message = "not_found", "Topilmadi."
    elif isinstance(exc, exceptions.MethodNotAllowed):
        code, message = "method_not_allowed", "Bu metod ruxsat etilmagan."
    elif isinstance(exc, exceptions.Throttled):
        code, message = "rate_limited", "So'rovlar juda ko'p."
    elif isinstance(exc, exceptions.ParseError):
        code, message = "bad_request", "So'rovni o'qib bo'lmadi."
    elif isinstance(exc, exceptions.UnsupportedMediaType):
        code, message = "unsupported_media_type", "Faqat JSON qabul qilinadi."
    headers = {k: str(v) for k, v in response.items() if k in {"Retry-After", "WWW-Authenticate"}}
    wrapped = error_response(code, message, status, details, headers)
    return Response(json.loads(wrapped.content), status=status, headers=headers)
