"""Nazoratchi'ning o'z zaxirasi (FR-SYS-003, NFR-SEC-010, TZ 14.10): reyestr, incident, audit, kanal va qoida sozlamalari
(metrikalarsiz) -> JSON -> gzip -> `age` bilan shifrlash (faqat OCHIQ kalit core'da) -> Telegram'da Owner'ning shaxsiy
chatiga fayl sifatida. Fayl 45 MB dan oshsa bo'laklanadi.

Tiklash: `manage.py restore_self_backup`. DIQQAT: kanal sirlari (`config_enc`) `NAZORATCHI_MASTER_KEY` bilan shifrlangan va
zaxiraga SHIFRLANGAN holda kiradi; master kalit zaxirada YO'Q — uni parol menejerida alohida saqlash shart (TZ 14.6).
"""

import gzip
import io
import logging
import time
from collections.abc import Callable
from datetime import datetime

import pyrage
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.notifications import telegram
from apps.notifications.models import Channel

from .models import SelfBackup

logger = logging.getLogger(__name__)

# Metrikalar, qayta hisoblanadigan holat va sessiyalar zaxiraga kirmaydi (hajm kichik, tiklash tez).
EXCLUDES = [
    "contenttypes", "sessions", "accounts.usersession", "metrics", "notifications.notification",
    "alerts.alertinstance", "alerts.evaluatorstate", "probes.certstatus", "probes.dnschange", "backups",
]  # fmt: skip
SEND_ATTEMPTS = 3


class SelfBackupError(Exception):
    pass


def build_archive() -> bytes:
    """Zaxira JSON ning gzip'langan ko'rinishi."""
    out = io.StringIO()
    args = [arg for e in EXCLUDES for arg in ("--exclude", e)]
    call_command("dumpdata", *args, "--format", "json", stdout=out)
    return gzip.compress(out.getvalue().encode(), compresslevel=6, mtime=0)


def encrypt(data: bytes, pubkey: str) -> bytes:
    try:
        recipient = pyrage.x25519.Recipient.from_str(pubkey)
    except Exception as exc:  # noqa: BLE001 - pyrage o'z istisnolarini ishlatadi
        raise SelfBackupError(
            "NAZORATCHI_BACKUP_AGE_PUBKEY yaroqli age ochiq kaliti emas (age1...)"
        ) from exc
    return bytes(pyrage.encrypt(data, [recipient]))


def split(data: bytes, size: int) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)] or [b""]


def decrypt(data: bytes, identity: str) -> bytes:
    try:
        ident = pyrage.x25519.Identity.from_str(identity.strip())
        return bytes(pyrage.decrypt(data, [ident]))
    except Exception as exc:  # noqa: BLE001
        raise SelfBackupError(
            "shifrni ochib bo'lmadi (maxfiy kalit noto'g'ri yoki fayl buzilgan)"
        ) from exc


def _send_part(
    token: str,
    chat_id: int | str,
    name: str,
    data: bytes,
    caption: str,
    sleep: Callable[[float], None],
) -> None:
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            telegram.send_document(token, chat_id, name, data, caption)
            return
        except telegram.TelegramError as exc:
            if not exc.retryable or attempt == SEND_ATTEMPTS:
                raise
            sleep(2.0**attempt)


def run(
    channel_name: str, now: datetime | None = None, sleep: Callable[[float], None] = time.sleep
) -> SelfBackup:
    """Zaxira olib yuboradi va natijani `SelfBackup` ga yozadi (muvaffaqiyatda ham, xatoda ham)."""
    now = now or timezone.now()
    pubkey = settings.NAZORATCHI_BACKUP_AGE_PUBKEY
    if not pubkey:
        raise SelfBackupError(
            "NAZORATCHI_BACKUP_AGE_PUBKEY sozlanmagan: shifrlanmagan zaxira yuborilmaydi"
        )
    channel = Channel.objects.filter(
        name=channel_name, type=Channel.Type.TELEGRAM, enabled=True
    ).first()
    if channel is None:
        raise SelfBackupError(
            f"Telegram kanali topilmadi: {channel_name!r} (Owner'ning shaxsiy chati kanali kerak)"
        )
    record = SelfBackup(created_at=now, channel_name=channel.name)
    try:
        cfg = channel.get_config()
        encrypted = encrypt(build_archive(), pubkey)
        parts = split(encrypted, settings.SELF_BACKUP_PART_BYTES)
        stamp = now.strftime("%Y%m%d-%H%M")
        for i, part in enumerate(parts, 1):
            suffix = f".part{i:02d}of{len(parts):02d}" if len(parts) > 1 else ""
            caption = f"Nazoratchi o'z zaxirasi {stamp} UTC" + (
                f" ({i}/{len(parts)})" if len(parts) > 1 else ""
            )
            _send_part(
                str(cfg["bot_token"]),
                cfg["chat_id"],
                f"nazoratchi-selfbackup-{stamp}.json.gz.age{suffix}",
                part,
                caption,
                sleep,
            )
        record.status, record.size_bytes, record.parts = (
            SelfBackup.Status.OK,
            len(encrypted),
            len(parts),
        )
    except (SelfBackupError, telegram.TelegramError, KeyError) as exc:
        record.status, record.error = SelfBackup.Status.FAILED, str(exc)[:300]
        logger.error("o'z zaxirasi yuborilmadi: %s", record.error)
    except Exception as exc:  # kutilmagan xato ham qayd etiladi (alert uchun), lekin matnda sir bo'lmasligi uchun faqat turi
        record.status, record.error = (
            SelfBackup.Status.FAILED,
            f"kutilmagan xato: {type(exc).__name__}",
        )
        logger.exception("o'z zaxirasi kutilmagan xato bilan tugadi")
    record.save()
    return record


def restore(parts: list[bytes], identity: str) -> str:
    """Bo'laklarni birlashtirib, shifrni ochadi va `loaddata` bilan yuklaydi. Qaytadi: loaddata chiqishi."""
    import tempfile
    from pathlib import Path

    raw = gzip.decompress(decrypt(b"".join(parts), identity))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "selfbackup.json"
        path.write_bytes(raw)
        out = io.StringIO()
        call_command("loaddata", str(path), stdout=out)
    return out.getvalue().strip()
