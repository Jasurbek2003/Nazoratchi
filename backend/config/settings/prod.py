"""Prod sozlamalari. Maxfiy qiymatlar faqat muhitdan (default yo'q)."""

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS, env

# Konteyner healthcheck va host watchdog (appctl) /healthz ga 127.0.0.1 orqali murojaat qiladi (TZ 6, 15.4).
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "127.0.0.1", "localhost"]

# TLS nginx'da tugaydi; so'rov `X-Forwarded-Proto` bilan keladi (TZ 15.6).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # yo'naltirishni nginx bajaradi; /healthz http orqali ham ochiladi
SESSION_COOKIE_NAME = "__Host-nzr_sid"  # __Host- prefiksi: Secure, Path=/, Domain yo'q (TZ 14.3.4)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
