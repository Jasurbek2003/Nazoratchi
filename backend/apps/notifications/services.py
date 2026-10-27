"""Xabarlarni navbatga qo'yish va yuborish (FR-NTF-001/004).

Oqim: `enqueue()` har mos kanal uchun `queued` qator yaratadi -> `deliver_due()` (worker) yuboradi.
Vaqtinchalik xatoda 5 martagacha eksponensial kutish bilan qayta uriniladi; doimiy xatoda (noto'g'ri
token/chat, bot bloklangan) darhol `failed`. Email zaxira kanali F2 da (FR-NTF-005).
"""

import logging
import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.crypto import DecryptionError

from . import telegram
from .messages import Message, channel_test_message, render
from .models import SEVERITY_RANK, Channel, Notification

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# 1-urinishdan keyin 5 s, 2-dan keyin 15 s, 3-dan keyin 1 daq, 4-dan keyin 5 daq (NFR-PRF-004: alert ~10 s).
RETRY_DELAYS_S = (5, 15, 60, 300)
MAX_ERROR_LEN = 300


def enqueue(
    msg: Message,
    *,
    event: str,
    incident_id: uuid.UUID | None = None,
    channels: list[Channel] | None = None,
) -> list[Notification]:
    """Ahamiyati kanalning `min_severity` dan past bo'lmagan yoqilgan kanallarga navbat yaratadi."""
    rank = SEVERITY_RANK.get(msg.severity, 0)
    if channels is None:
        channels = list(Channel.objects.filter(enabled=True))
    payload = render(msg)
    now = timezone.now()
    rows = [
        Notification(
            incident_id=incident_id,
            channel=ch,
            event=event,
            payload=payload,
            created_at=now,
            next_attempt_at=now,
        )
        for ch in channels
        if ch.enabled and SEVERITY_RANK.get(ch.min_severity, 0) <= rank
    ]
    return Notification.objects.bulk_create(rows)


def _attempt(n: Notification, now: datetime) -> None:
    """Bitta urinish: natijani `n` va kanal holatiga yozadi (saqlashni chaqiruvchi qiladi)."""
    channel = n.channel
    n.attempts += 1
    try:
        if channel.type != Channel.Type.TELEGRAM:
            raise telegram.TelegramError(
                f"{channel.type} kanali hali qo'llab-quvvatlanmaydi", retryable=False
            )
        try:
            cfg = channel.get_config()
        except DecryptionError as exc:
            # Kalit almashtirilgan yoki ma'lumot buzilgan: qayta urinish befoyda, kanalni qayta kiritish kerak.
            raise telegram.TelegramError(str(exc), retryable=False) from exc
        sent = telegram.send_message(
            cfg["bot_token"], cfg["chat_id"], n.payload["text"], n.payload.get("buttons")
        )
    except telegram.TelegramError as exc:
        n.error = str(exc)[:MAX_ERROR_LEN]
        channel.last_error = n.error
        if exc.retryable and n.attempts < MAX_ATTEMPTS:
            delay = exc.retry_after or RETRY_DELAYS_S[min(n.attempts - 1, len(RETRY_DELAYS_S) - 1)]
            n.next_attempt_at = now + timedelta(seconds=delay)
            logger.warning(
                "bildirishnoma yuborilmadi (urinish %s/%s): %s", n.attempts, MAX_ATTEMPTS, n.error
            )
        else:
            n.status = Notification.Status.FAILED
            logger.error("bildirishnoma yuborilmadi, qayta urinilmaydi: %s", n.error)
        return
    n.status = Notification.Status.SENT
    n.sent_at = now
    n.external_id = sent.message_id
    n.error = ""
    channel.last_ok_at = now
    channel.last_error = ""


def deliver(n: Notification, now: datetime | None = None) -> Notification:
    now = now or timezone.now()
    _attempt(n, now)
    n.save(
        update_fields=["status", "attempts", "sent_at", "external_id", "error", "next_attempt_at"]
    )
    n.channel.save(update_fields=["last_ok_at", "last_error"])
    return n


def deliver_due(limit: int = 50, now: datetime | None = None) -> int:
    """Vaqti kelgan `queued` xabarlarni yuboradi; qaytadi: urinishlar soni. Bir nechta worker xavfsiz
    (`SKIP LOCKED`): har xabar bitta tranzaksiyada, qator qulflangan holda yuboriladi."""
    done = 0
    for _ in range(limit):
        with transaction.atomic():
            current = now or timezone.now()
            n = (
                Notification.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("channel")
                .filter(status=Notification.Status.QUEUED, next_attempt_at__lte=current)
                .order_by("next_attempt_at", "id")
                .first()
            )
            if n is None:
                break
            deliver(n, current)
        done += 1
    return done


def send_test(channel: Channel) -> Notification:
    """Panel tugmasi (FR-ALR-020): bitta urinish, darhol natija; qayta urinish yo'q."""
    now = timezone.now()
    n = Notification.objects.create(
        channel=channel,
        event="test",
        payload=render(channel_test_message(channel.name)),
        created_at=now,
        next_attempt_at=now,
    )
    _attempt(n, now)
    if n.status == Notification.Status.QUEUED:  # vaqtinchalik xato: sinovda qayta urinilmaydi
        n.status = Notification.Status.FAILED
    n.save()
    channel.save(update_fields=["last_ok_at", "last_error"])
    return n
