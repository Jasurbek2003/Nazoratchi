"""`POST /api/v1/telegram/webhook/{secret}` (TZ 9.12): inline tugmalar — "Qabul qilaman", "1 soat jim".

Talablar: maxfiy URL segmenti VA `X-Telegram-Bot-Api-Secret-Token` sarlavhasi; chat kanallardan birining chat ID siga
teng bo'lishi; `callback_data` HMAC bilan imzolangan. Javob har doim 200 (Telegram qayta yubormasligi uchun);
ruxsatsiz so'rov faqat loglanadi.
"""

import hmac
import json
import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.audit.services import record
from apps.core.crypto import DecryptionError

from . import callbacks, telegram
from .models import Channel

logger = logging.getLogger(__name__)
SNOOZE_MIN, SNOOZE_MAX = 15, 24 * 60
MAX_BODY = 16 * 1024


def _ok() -> JsonResponse:
    return JsonResponse({})


def _equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _channel_for_chat(chat_id: int) -> tuple[Channel, str] | None:
    """Chat ID ruxsat etilgan kanallardan birinikimi? Qaytadi: (kanal, bot_token)."""
    for channel in Channel.objects.filter(type=Channel.Type.TELEGRAM, enabled=True):
        try:
            cfg = channel.get_config()
        except DecryptionError:
            continue
        if cfg.get("chat_id") == chat_id:
            return channel, str(cfg["bot_token"])
    return None


def _snooze_matchers(incident: Any) -> list[dict[str, str]]:
    from apps.registry.models import Project, Server

    kind, _, ident = incident.scope_key.partition(":")
    if kind == "host" and (server := Server.objects.filter(pk=ident).first()):
        return [{"label": "server", "op": "=", "value": server.name}]
    if kind == "project" and (project := Project.objects.filter(pk=ident).first()):
        return [{"label": "project", "op": "=", "value": project.name}]
    alert = incident.alerts.select_related("rule").first()
    return [{"label": "rule", "op": "=", "value": alert.rule.key}] if alert else []


def _act(
    action: str, incident_id: str, extra: list[str], user: User | None, tg_user: dict[str, Any]
) -> str:
    from apps.alerts import services
    from apps.alerts.models import Incident, Silence

    incident = Incident.objects.filter(pk=incident_id).first()
    if incident is None:
        return "Incident topilmadi."
    who = f"telegram:{tg_user.get('username') or tg_user.get('id')}"
    if action == "ack":
        try:
            services.ack(incident, user, f"Telegram ({who})")
        except services.IncidentConflict as exc:
            return str(exc)
        record(
            "incident.ack",
            user=user,
            object_type="incident",
            object_id=incident.pk,
            after={"via": who},
        )
        return "Qabul qilindi ✅"
    if action == "snz":
        minutes = int(extra[0]) if extra and extra[0].isdigit() else 60
        if not SNOOZE_MIN <= minutes <= SNOOZE_MAX:
            return "Muddat noto'g'ri."
        matchers = _snooze_matchers(incident)
        if incident.status == Incident.Status.RESOLVED or not matchers:
            return "Jim qilib bo'lmaydi."
        now = timezone.now()
        silence = Silence.objects.create(
            matchers=matchers, starts_at=now, ends_at=now + timedelta(minutes=minutes),
            reason=f"Telegram: {minutes} daqiqa jim ({who})", created_by=user,
        )  # fmt: skip
        record(
            "silence.create",
            user=user,
            object_type="silence",
            object_id=silence.pk,
            after={"via": who, "minutes": minutes},
        )
        return f"{minutes} daqiqa jim qilindi 🔕"
    return "Noma'lum amal."


@csrf_exempt
@require_POST
def webhook(request: HttpRequest, secret: str) -> JsonResponse:
    configured = settings.TELEGRAM_WEBHOOK_SECRET
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not configured or not _equal(secret, configured) or not _equal(header, configured):
        logger.warning("telegram webhook: maxfiy kalit mos emas yoki webhook o'chiq")
        return _ok()
    if len(request.body) > MAX_BODY:
        return _ok()
    try:
        update = json.loads(request.body)
        query = update["callback_query"]
        chat_id = int(query["message"]["chat"]["id"])
        tg_user = dict(query.get("from") or {})
        data = str(query["data"])
        query_id = str(query["id"])
    except (ValueError, KeyError, TypeError):
        return _ok()  # boshqa yangilanishlar (xabarlar, buyruqlar — F2) e'tiborsiz

    found = _channel_for_chat(chat_id)
    if found is None:
        logger.warning("telegram webhook: begona chat %s", chat_id)
        return _ok()
    _, bot_token = found
    parsed = callbacks.parse(data)
    if parsed is None:
        logger.warning("telegram webhook: imzo noto'g'ri")
        return _ok()
    user = (
        User.objects.filter(telegram_chat_id=tg_user.get("id"), is_active=True).first()
        if tg_user.get("id")
        else None
    )
    if user is not None and user.role == "viewer":
        text = "Sizda bu amalga ruxsat yo'q."
    else:
        text = _act(*parsed, user=user, tg_user=tg_user)
    try:
        telegram.answer_callback(bot_token, query_id, text)
    except telegram.TelegramError as exc:
        logger.warning("telegram javobi yuborilmadi: %s", exc)
    return _ok()
