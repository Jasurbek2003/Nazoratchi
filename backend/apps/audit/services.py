"""Audit yozuvi: maxfiy maydonlar maskalanadi (FR-AUD-002: parol/token qiymatlari jurnalda yo'q)."""

import json
import re
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest

from apps.core.net import client_ip

from .models import AuditLog

_SECRET_KEY = re.compile(r"(?i)password|passwd|token|secret|authorization|api_?key|private_?key")
MASK = "***"


def mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: MASK if _SECRET_KEY.search(str(k)) else mask(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [mask(v) for v in value]
    return value


def _jsonable(value: Any) -> Any:
    """UUID, datetime, Decimal kabi turlar JSON ga o'giriladi (serializer `.data` ularni xom holda qoldiradi)."""
    if value is None:
        return None
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def record(
    action: str,
    *,
    request: HttpRequest | None = None,
    user: Any = None,
    ip: str | None = None,
    object_type: str = "",
    object_id: object = "",
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    if request is not None:
        if user is None and getattr(request, "user", None) and request.user.is_authenticated:
            user = request.user
        ip = ip or client_ip(request)
    return AuditLog.objects.create(
        user=user,
        ip=ip,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id != "" else "",
        before=mask(_jsonable(before)),
        after=mask(_jsonable(after)),
    )
