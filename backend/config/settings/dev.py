"""Dev sozlamalari: `deploy/docker-compose.dev.yml` bazasi va Redis'iga ulanadi."""

import os

os.environ.setdefault("SECRET_KEY", "dev-insecure-key-faqat-ishlab-chiqish-uchun-0123456789abcdef")
os.environ.setdefault("DB_PASSWORD", "dev")
# Faqat dev/test: 32 bayt (base64). Prod'da haqiqiy kalit .env dan keladi.
os.environ.setdefault("NAZORATCHI_MASTER_KEY", "ZGV2LWtleS1mYXFhdC1pc2hsYWItY2hpcWlzaC0wMDA=")
os.environ.setdefault("DB_HOST", "127.0.0.1")  # "localhost" Windows da IPv6 sabab sekin
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6380/0")

from .base import *  # noqa: E402, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
