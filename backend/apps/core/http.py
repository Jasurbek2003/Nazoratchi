"""Yagona xato formati (TZ 9.1.1)."""

import uuid

from django.http import JsonResponse


def error_response(
    code: str,
    message: str,
    status: int,
    details: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JsonResponse:
    body: dict[str, object] = {
        "code": code,
        "message": message,
        "request_id": "req_" + uuid.uuid4().hex[:12],
    }
    if details:
        body["details"] = details
    response = JsonResponse({"error": body}, status=status)
    for key, value in (headers or {}).items():
        response[key] = value
    return response
