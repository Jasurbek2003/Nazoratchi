"""Mijoz IP manzili. Proksi sarlavhalariga faqat `TRUST_PROXY_HEADERS` yoqilganda ishoniladi."""

from django.conf import settings
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str | None:
    """nginx `X-Forwarded-For` ga mijoz manzilini OXIRGI element qilib qo'shadi (`$proxy_add_x_forwarded_for`),
    shuning uchun mijoz yuborgan soxta qiymatlar emas, o'ng tomondagisi olinadi."""
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[-1].strip() or None
    addr = request.META.get("REMOTE_ADDR")
    return str(addr) if addr else None
