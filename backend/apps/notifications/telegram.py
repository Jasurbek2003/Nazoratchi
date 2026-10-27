"""Telegram Bot API klienti (FR-NTF-001). Bot tokeni URL ichida bo'lgani uchun hech qachon logga yoki
xato matniga tushmaydi (TZ 14.9)."""

from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

TIMEOUT_S = 10.0


class TelegramError(Exception):
    """`retryable` — vaqtinchalik xato (tarmoq, 5xx, 429); aks holda (noto'g'ri token/chat, bot bloklangan)
    qayta urinish befoyda."""

    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class Sent:
    message_id: str


def make_client() -> httpx.Client:
    """Testlarda almashtiriladi (`httpx.MockTransport`)."""
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def answer_callback(bot_token: str, callback_id: str, text: str) -> None:
    """Tugma bosilganda foydalanuvchiga qisqa javob (toast). Xatoda `TelegramError`."""
    url = f"{settings.TELEGRAM_API_BASE}/bot{bot_token}/answerCallbackQuery"
    try:
        with make_client() as client:
            response = client.post(url, json={"callback_query_id": callback_id, "text": text[:200]})
    except httpx.HTTPError as exc:
        raise TelegramError(
            f"tarmoq xatosi: {_redact(type(exc).__name__, bot_token)}", retryable=True
        ) from None
    if response.status_code != 200:
        raise TelegramError(f"HTTP {response.status_code}", retryable=response.status_code >= 500)


def send_message(
    bot_token: str,
    chat_id: int | str,
    text: str,
    buttons: list[dict[str, str]] | None = None,
) -> Sent:
    """HTML rejimida yuboradi. `buttons` — [{"text":..., "url":...}], bir qatorda."""
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if buttons:
        body["reply_markup"] = {"inline_keyboard": [buttons]}
    url = f"{settings.TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    try:
        with make_client() as client:
            response = client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise TelegramError(
            f"tarmoq xatosi: {_redact(type(exc).__name__ + ': ' + str(exc), bot_token)}",
            retryable=True,
        ) from None

    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code == 200 and data.get("ok"):
        return Sent(str(data.get("result", {}).get("message_id", "")))

    description = _redact(str(data.get("description", "")), bot_token)[:200]
    if response.status_code == 429:
        retry_after = data.get("parameters", {}).get("retry_after")
        raise TelegramError(
            f"HTTP 429: {description}",
            retryable=True,
            retry_after=float(retry_after) if isinstance(retry_after, int | float) else None,
        )
    raise TelegramError(
        f"HTTP {response.status_code}: {description}",
        retryable=response.status_code >= 500,
    )
