"""Test sozlamalari: tez xesh, xotiradagi kesh (Redis kerak emas)."""

from .dev import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # faqat testlarda (tezlik)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
