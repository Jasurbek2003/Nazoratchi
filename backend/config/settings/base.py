"""Umumiy sozlamalar. Barcha qiymatlar muhit o'zgaruvchilaridan (12-factor, NFR-MNT-004)."""

import base64
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Muhit o'zgaruvchisi o'rnatilmagan: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, "1" if default else "0").lower() in ("1", "true", "yes", "on")


def master_key(raw: str) -> bytes:
    """`NAZORATCHI_MASTER_KEY`: base64, aynan 32 bayt (AES-256-GCM, TZ 14.6). Noto'g'ri bo'lsa ishga tushmaydi."""
    try:
        key = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise ImproperlyConfigured("NAZORATCHI_MASTER_KEY base64 emas.") from exc
    if len(key) != 32:
        raise ImproperlyConfigured("NAZORATCHI_MASTER_KEY aynan 32 bayt bo'lishi kerak.")
    return key


SECRET_KEY = env("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [h for h in env("ALLOWED_HOSTS", "").split(",") if h]
PUBLIC_URL = env("PUBLIC_URL", "http://127.0.0.1:8000").rstrip(
    "/"
)  # alert havolalari, install buyrug'i
NAZORATCHI_MASTER_KEY = master_key(
    env("NAZORATCHI_MASTER_KEY")
)  # kanal sirlarini shifrlash (TZ 14.6)
TELEGRAM_API_BASE = env("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS")  # nginx orqasida True (X-Forwarded-For)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.registry",
    "apps.metrics",
    "apps.ingest",
    "apps.heartbeats",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AbsoluteSessionTimeoutMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "nazoratchi"),
        "USER": env("DB_USER", "nazoratchi"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
}

# Kesh Redis tushsa ham ishlaydi (fail-open): tezlik chegarasi va throttling uchun (NFR-REL-004).
CACHES = {
    "default": {
        "BACKEND": "apps.core.cache.FailOpenRedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    }
}

# --- Autentifikatsiya (TZ 14.3) ---
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = ["apps.accounts.hashers.NazoratchiArgon2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_ENGINE = "apps.accounts.sessions"
SESSION_COOKIE_NAME = "nzr_sid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = (
    12 * 3600
)  # harakatsizlik muddati; mutlaq 7 kun — AbsoluteSessionTimeoutMiddleware
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_SAMESITE = "Lax"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.core.permissions.DenyByDefault"
    ],  # e'lon qilinmagan endpoint rad etiladi
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.api.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "120/min", "login": "10/min"},  # TZ 9.1, NFR-SEC-007
    "NUM_PROXIES": 1 if TRUST_PROXY_HEADERS else 0,
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Ichkarida hamma vaqt UTC (NFR-REL-008); foydalanuvchi zonasi UI da qo'llanadi.
LANGUAGE_CODE = "uz"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    # httpx so'rov URL'ini INFO da yozadi, Telegram URL'i esa bot tokenini o'z ichiga oladi (TZ 14.9).
    "loggers": {"httpx": {"level": "WARNING"}, "httpcore": {"level": "WARNING"}},
}
