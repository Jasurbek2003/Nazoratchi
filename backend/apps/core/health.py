"""Core sog'ligi (FR-SYS-001/002/005): `/readyz`, `/metrics` va watchdog'ga yuboriladigan holat.

`/healthz` — jonlilik (faqat baza). `/readyz` — tayyorlik: baza, Redis, bildirishnoma navbati, alert dvigateli.
Watchdog'ga ketadigan holat (`ok`/`degraded`) shu tekshiruvlarning dvigateldan tashqari qismi (dvigatel pingni o'zi
yuboradi: u qotsa ping to'xtaydi — watchdog shuni ushlaydi, AL-084).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis
from django.conf import settings
from django.db import DatabaseError, connection
from django.utils import timezone

logger = logging.getLogger(__name__)

NOTIFY_STUCK_AFTER = timedelta(
    minutes=5
)  # `queued` xabar shundan ko'p kutsa, yuboruvchi (notifier) ishlamayapti
EVALUATOR_STALE_AFTER = timedelta(
    seconds=90
)  # dvigatel davri 15 s; 90 s dan eski = qotgan (AL-084 chegarasi 60 s + zaxira)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def check_db() -> Check:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("readyz: baza mavjud emas")
        return Check("db", False, "baza javob bermayapti")
    return Check("db", True)


def check_redis() -> Check:
    try:
        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1).ping()
    except Exception as exc:  # noqa: BLE001 - har qanday ulanish xatosi "tayyor emas"
        return Check("redis", False, type(exc).__name__)
    return Check("redis", True)


def check_notifier(now: datetime) -> Check:
    from apps.notifications.models import Notification

    oldest = (
        Notification.objects.filter(status=Notification.Status.QUEUED)
        .order_by("next_attempt_at")
        .values_list("next_attempt_at", flat=True)
        .first()
    )
    if oldest is not None and now - oldest > NOTIFY_STUCK_AFTER:
        return Check(
            "notifier",
            False,
            f"navbatdagi xabar {int((now - oldest).total_seconds() // 60)} daqiqa yuborilmagan",
        )
    return Check("notifier", True)


def check_evaluator(now: datetime) -> Check:
    from apps.alerts.models import EvaluatorState

    state = EvaluatorState.objects.filter(pk=1).first()
    if state is None:
        return Check("evaluator", False, "dvigatel hali ishga tushmagan")
    age = now - state.last_run_at
    if age > EVALUATOR_STALE_AFTER:
        return Check(
            "evaluator", False, f"dvigatel {int(age.total_seconds())} s dan beri davr bajarmadi"
        )
    return Check("evaluator", True)


def readiness(now: datetime | None = None) -> list[Check]:
    now = now or timezone.now()
    db = check_db()
    checks = [db, check_redis()]
    if db.ok:  # baza yo'q bo'lsa qolgan tekshiruvlar ma'nosiz
        checks += [check_notifier(now), check_evaluator(now)]
    return checks


def watchdog_status(now: datetime | None = None) -> tuple[str, str]:
    """Watchdog pingi uchun: ("ok" | "degraded", sabab). Dvigatel tekshiruvi kirmaydi (ping uning o'zidan keladi)."""
    now = now or timezone.now()
    db = check_db()
    problems = [] if db.ok else [f"{db.name}: {db.detail}"]
    if db.ok:
        problems += [
            f"{c.name}: {c.detail}" for c in (check_redis(), check_notifier(now)) if not c.ok
        ]
    return ("degraded", "; ".join(problems)[:100]) if problems else ("ok", "")
