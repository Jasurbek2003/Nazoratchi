"""Dev sozlamalari: `deploy/docker-compose.dev.yml` bazasiga ulanadi."""

import os

os.environ.setdefault("SECRET_KEY", "dev-insecure-key-faqat-ishlab-chiqish-uchun-0123456789abcdef")
os.environ.setdefault("DB_PASSWORD", "dev")
os.environ.setdefault("DB_HOST", "127.0.0.1")  # "localhost" Windows da IPv6 sabab sekin
os.environ.setdefault("DB_PORT", "5433")

from .base import *  # noqa: E402, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
