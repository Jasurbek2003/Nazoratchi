"""Konfiguratsiya: faqat muhit o'zgaruvchilari (env) orqali. Xato bo'lsa aniq o'zbekcha xabar."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")
CHAT_RE = re.compile(r"^(-?\d{3,20}|@[A-Za-z][A-Za-z0-9_]{4,})$")
API_RE = re.compile(r"^https?://[^\s/]+$")

DEFAULT_LISTEN = "127.0.0.1:8099"
DEFAULT_TIMEOUT_S = 300
DEFAULT_REMIND_S = 1800
DEFAULT_STATE_FILE = "/var/lib/nazoratchi-watchdog/state.json"
DEFAULT_TELEGRAM_API = "https://api.telegram.org"


class ConfigError(Exception):
    """Sozlama xatolari ro'yxati (hammasi bir vaqtda ko'rsatiladi)."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Config:
    watchdog_id: str
    bot_token: str
    chat_id: str
    host: str
    port: int
    timeout_s: int
    remind_s: int
    state_file: Path
    telegram_api: str


def _int(
    env: Mapping[str, str], name: str, default: int, lo: int, hi: int, problems: list[str]
) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{name}: butun son bo'lishi kerak (hozir: {raw!r}).")
        return default
    if not lo <= value <= hi:
        problems.append(f"{name}: {lo} dan {hi} gacha bo'lishi kerak (hozir: {value}).")
    return value


def load_config(env: Mapping[str, str]) -> Config:
    problems: list[str] = []

    watchdog_id = env.get("WATCHDOG_ID", "").strip()
    if not watchdog_id:
        problems.append("WATCHDOG_ID: berilmagan (ping manzilidagi maxfiy id).")
    elif not ID_RE.match(watchdog_id):
        problems.append("WATCHDOG_ID: 16-64 ta belgi, faqat A-Z a-z 0-9 _ - bo'lishi kerak.")

    token = env.get("WATCHDOG_BOT_TOKEN", "").strip()
    if not token:
        problems.append("WATCHDOG_BOT_TOKEN: berilmagan (@BotFather bergan mustaqil bot tokeni).")
    elif not TOKEN_RE.match(token):
        problems.append("WATCHDOG_BOT_TOKEN: format noto'g'ri (kutilgan: 123456:ABC...).")

    chat_id = env.get("WATCHDOG_CHAT_ID", "").strip()
    if not chat_id:
        problems.append("WATCHDOG_CHAT_ID: berilmagan (Telegram chat ID).")
    elif not CHAT_RE.match(chat_id):
        problems.append(
            "WATCHDOG_CHAT_ID: butun son (masalan -1001234567890) yoki @kanal bo'lishi kerak."
        )

    host, port = "127.0.0.1", 8099
    listen = env.get("WATCHDOG_LISTEN", "").strip() or DEFAULT_LISTEN
    host_part, sep, port_part = listen.rpartition(":")
    if not sep or not host_part or not port_part.isdigit() or not 1 <= int(port_part) <= 65535:
        problems.append(
            f"WATCHDOG_LISTEN: 'host:port' ko'rinishida bo'lishi kerak (hozir: {listen!r})."
        )
    else:
        host, port = host_part.strip("[]"), int(port_part)

    timeout_s = _int(env, "WATCHDOG_TIMEOUT_S", DEFAULT_TIMEOUT_S, 1, 86400, problems)
    remind_s = _int(env, "WATCHDOG_REMIND_S", DEFAULT_REMIND_S, 1, 604800, problems)

    state_raw = env.get("WATCHDOG_STATE_FILE", "").strip() or DEFAULT_STATE_FILE
    api = (env.get("WATCHDOG_TELEGRAM_API", "").strip() or DEFAULT_TELEGRAM_API).rstrip("/")
    if not API_RE.match(api):
        problems.append("WATCHDOG_TELEGRAM_API: 'https://host[:port]' ko'rinishida bo'lishi kerak.")

    if problems:
        raise ConfigError(problems)
    return Config(
        watchdog_id=watchdog_id,
        bot_token=token,
        chat_id=chat_id,
        host=host,
        port=port,
        timeout_s=timeout_s,
        remind_s=remind_s,
        state_file=Path(state_raw),
        telegram_api=api,
    )
