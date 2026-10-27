"""Alert dvigateli (TZ 6.7, 12): har davrda qoidalarni hisoblaydi, holat mashinasini yuritadi, incidentlarni
ochadi/yopadi, bostirishni qo'llaydi va bildirishnomalarni navbatga qo'yadi.

Davr ikki bosqichda: (1) barcha qoidalar bo'yicha holatlar yangilanadi; (2) shundan KEYIN bildirishnomalar
qaror qilinadi. Shunda bog'liqlik bostirishi ("host o'chdi" -> uning boshqa alertlari) bir davrda to'g'ri ishlaydi.
Bitta qoidadagi xato qolganlarni to'xtatmaydi.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications import services as notifications
from apps.notifications.models import SEVERITY_RANK, Channel

from .conditions import Ctx, Subject, evaluate_rule
from .messages import alert_message, alert_title, reminder_message, resolved_message
from .models import AlertInstance, AlertRule, EvaluatorState, Incident, IncidentEvent
from .suppression import SuppressionContext

logger = logging.getLogger(__name__)

# Takroriy eslatmalar (12.4.1): ahamiyat -> (interval, soni). critical: 30 daqiqada 6 marta, keyin 2 soatda bir.
REMINDERS = {
    "critical": (timedelta(minutes=30), 6, timedelta(hours=2)),
    "high": (timedelta(hours=2), 3, None),
    "warning": (timedelta(hours=24), 7, None),
}
OPEN_STATES = (AlertInstance.State.FIRING, AlertInstance.State.RESOLVING)


@dataclass
class CycleStats:
    rules: int = 0
    rule_errors: int = 0
    notified: int = 0
    reminders: int = 0
    incidents_opened: int = 0
    incidents_resolved: int = 0


def fingerprint(rule: AlertRule, subject: Subject) -> str:
    return hashlib.sha1(
        f"{rule.pk}|{subject.type}|{subject.id}".encode(), usedforsecurity=False
    ).hexdigest()


def _event(
    incident: Incident, type_: str, now: datetime, user: object = None, **data: object
) -> None:
    IncidentEvent.objects.create(incident=incident, type=type_, time=now, user=user, data=data)  # type: ignore[misc]


# ----------------------------------------------------------------------- holat mashinasi (6.7.1)
def _open_incident(
    rule: AlertRule, inst: AlertInstance, scope_key: str, now: datetime
) -> tuple[Incident, bool]:
    incident = (
        Incident.objects.filter(scope_key=scope_key)
        .exclude(status=Incident.Status.RESOLVED)
        .first()
    )
    if incident is None:
        try:
            with transaction.atomic():
                incident = Incident.objects.create(
                    scope_key=scope_key,
                    title=alert_title(inst),
                    severity=rule.severity,
                    started_at=inst.pending_since or now,
                )
            _event(incident, "opened", now, alert=rule.key)
            return incident, True
        except IntegrityError:  # parallel dvigatel yaratib qo'ygan
            incident = (
                Incident.objects.filter(scope_key=scope_key)
                .exclude(status=Incident.Status.RESOLVED)
                .get()
            )
    _event(incident, "alert_added", now, alert=rule.key, subject=inst.subject_name)
    if SEVERITY_RANK[rule.severity] > SEVERITY_RANK[incident.severity]:
        old = incident.severity
        incident.severity, incident.title = rule.severity, alert_title(inst)
        if incident.status == Incident.Status.ACKNOWLEDGED:  # ahamiyat oshsa qayta xabar (12.4.3)
            incident.status, incident.acked_at, incident.acked_by = Incident.Status.OPEN, None, None
        incident.reminders_sent = 0
        incident.save(
            update_fields=["severity", "title", "status", "acked_at", "acked_by", "reminders_sent"]
        )
        _event(incident, "severity_changed", now, old=old, new=rule.severity)
    return incident, False


def _transition(
    inst: AlertInstance,
    rule: AlertRule,
    condition: bool,
    now: datetime,
    scope_key: str,
    stats: CycleStats,
) -> None:
    S = AlertInstance.State
    if condition:
        if inst.state == S.OK:
            inst.state, inst.pending_since = S.PENDING, now
        elif inst.state == S.RESOLVING:
            inst.state, inst.resolving_since = S.FIRING, None
        if (
            inst.state == S.PENDING
            and (now - (inst.pending_since or now)).total_seconds() >= rule.for_seconds
        ):
            # pending_since saqlanadi: muammo `for` boshlangan paytdan beri bor (davomiylik va "qachondan" uchun).
            inst.state, inst.firing_since = S.FIRING, now
            inst.notified_at, inst.suppressed = None, False
            incident, opened = _open_incident(rule, inst, scope_key, now)
            inst.incident = incident
            stats.incidents_opened += opened
    else:
        if inst.state == S.PENDING:
            inst.state, inst.pending_since = S.OK, None
        elif inst.state == S.FIRING:
            inst.state, inst.resolving_since = S.RESOLVING, now
        if (
            inst.state == S.RESOLVING
            and (now - (inst.resolving_since or now)).total_seconds() >= rule.resolve_after_seconds
        ):
            inst.state, inst.firing_since, inst.resolving_since = S.OK, None, None
            inst.pending_since = None
            if inst.incident is not None:
                _event(
                    inst.incident, "alert_resolved", now, alert=rule.key, subject=inst.subject_name
                )


def _apply(rule: AlertRule, subject: Subject, now: datetime, stats: CycleStats) -> str:
    fp = fingerprint(rule, subject)
    inst, _ = AlertInstance.objects.select_related("incident").get_or_create(
        fingerprint=fp,
        defaults={
            "rule": rule,
            "subject_type": subject.type,
            "subject_id": subject.id,
            "last_eval_at": now,
        },
    )
    inst.subject_name, inst.labels, inst.last_eval_at = subject.name, subject.labels, now
    inst.last_value, inst.detail = subject.value, subject.detail[:300]
    if subject.firing is not None:
        _transition(inst, rule, subject.firing, now, subject.scope_key, stats)
    elif inst.state == AlertInstance.State.PENDING:
        # Ma'lumot yo'q: `for` davomidagi uzluksizlik tasdiqlanmadi. Aks holda agent bir soatdan keyin qaytganda
        # eski pending darrov firing bo'lardi. Firing/resolving holatlar esa o'zgarmaydi.
        inst.state, inst.pending_since = AlertInstance.State.OK, None
    inst.save()
    return fp


def _evaluate_states(now: datetime, stats: CycleStats) -> None:
    ctx = Ctx(now)
    rules = list(AlertRule.objects.all())
    for rule in rules:
        if not rule.enabled:
            seen: set[str] = set()  # o'chirilgan qoidaning ochiq alertlari yopiladi
        else:
            stats.rules += 1
            try:
                subjects = evaluate_rule(rule, ctx)
                with transaction.atomic():
                    seen = {_apply(rule, s, now, stats) for s in subjects}
            except Exception:
                stats.rule_errors += 1
                logger.exception("qoida hisoblanmadi: %s", rule.key)
                continue
        # Obyekti yo'qolgan (server arxivlandi, mount ketdi) yoki qoida o'chirilgan alertlar: shart yolg'on.
        gone = (
            AlertInstance.objects.filter(rule=rule)
            .exclude(state=AlertInstance.State.OK)
            .exclude(fingerprint__in=seen)
            .select_related("incident")
        )
        for inst in gone:
            with transaction.atomic():
                _transition(inst, rule, False, now, "", stats)
                inst.last_eval_at = now
                inst.save()


# ----------------------------------------------------------------------- bildirishnomalar
def _channels_for(rule: AlertRule) -> list[Channel] | None:
    if not rule.channels:
        return None
    return list(Channel.objects.filter(pk__in=rule.channels, enabled=True))


def _notify_phase(now: datetime, stats: CycleStats) -> None:
    pending = list(
        AlertInstance.objects.filter(state=AlertInstance.State.FIRING, notified_at__isnull=True)
        .select_related("rule", "incident")
        .order_by("firing_since")
    )
    if not pending:
        return
    sup = SuppressionContext(now)
    for inst in pending:
        reason = sup.reason(inst)
        inst.suppressed = bool(reason)
        if reason:
            inst.save(update_fields=["suppressed"])
            continue
        incident = inst.incident
        if incident is None:  # firing alert doim incidentga bog'langan; himoya
            continue
        # Bir davrda bir nechta alert bir incidentga tushsa, har biri o'z nusxasini ko'radi: yangilab olamiz.
        incident.refresh_from_db(fields=["last_notified_at"])
        first = incident.last_notified_at is None
        msg = alert_message(inst, joined=not first)
        notifications.enqueue(
            msg,
            event="opened" if first else "alert_added",
            incident_id=incident.pk,
            channels=_channels_for(inst.rule),
        )
        inst.notified_at = now
        inst.save(update_fields=["suppressed", "notified_at"])
        incident.last_notified_at = now
        incident.save(update_fields=["last_notified_at"])
        _event(incident, "notified", now, alert=inst.rule.key, subject=inst.subject_name)
        stats.notified += 1


def _active(incident: Incident) -> list[AlertInstance]:
    return list(incident.alerts.filter(state__in=OPEN_STATES).select_related("rule"))


def _refresh_suppressed(now: datetime) -> None:
    """Incident `suppressed` — barcha faol alertlari bostirilgan bo'lsa."""
    for incident in Incident.objects.exclude(status=Incident.Status.RESOLVED):
        active = [a for a in _active(incident) if a.state == AlertInstance.State.FIRING]
        flag = bool(active) and all(a.suppressed for a in active)
        if flag != incident.suppressed:
            incident.suppressed = flag
            incident.save(update_fields=["suppressed"])


def _reminders(now: datetime, stats: CycleStats) -> None:
    for incident in Incident.objects.filter(
        status=Incident.Status.OPEN, last_notified_at__isnull=False, suppressed=False
    ):
        policy = REMINDERS.get(incident.severity)
        if policy is None:
            continue
        interval, count, later = policy
        wait = interval if incident.reminders_sent < count else later
        if (
            wait is None
            or incident.last_notified_at is None
            or now - incident.last_notified_at < wait
        ):
            continue
        active = [
            a
            for a in _active(incident)
            if a.state == AlertInstance.State.FIRING and not a.suppressed
        ]
        if not active:
            continue
        notifications.enqueue(
            reminder_message(incident, active, now), event="reminder", incident_id=incident.pk
        )
        incident.last_notified_at, incident.reminders_sent = now, incident.reminders_sent + 1
        incident.save(update_fields=["last_notified_at", "reminders_sent"])
        _event(incident, "reminder", now, n=incident.reminders_sent)
        stats.reminders += 1


def _close_incidents(now: datetime, stats: CycleStats) -> None:
    for incident in Incident.objects.exclude(status=Incident.Status.RESOLVED):
        if (
            incident.alerts.filter(state__in=OPEN_STATES).exists()
            or incident.alerts.filter(state=AlertInstance.State.PENDING).exists()
        ):
            continue
        incident.status, incident.resolved_at = Incident.Status.RESOLVED, now
        incident.save(update_fields=["status", "resolved_at"])
        _event(incident, "resolved", now)
        stats.incidents_resolved += 1
        # "Tiklandi" faqat odamga xabar berilgan bo'lsa (FR-ALR-014).
        if incident.alerts.filter(notified_at__isnull=False).exists():
            notifications.enqueue(
                resolved_message(incident, now), event="resolved", incident_id=incident.pk
            )


def _resume_expired_pauses(now: datetime) -> None:
    """`until` bilan pauzaga qo'yilgan serverlar muddati tugagach o'zi davom etadi (FR-HST-016)."""
    from apps.registry.models import Server
    from apps.registry.server_actions import resume

    for server in Server.objects.filter(status=Server.Status.PAUSED, paused_until__lte=now):
        resume(server, "tizim (muddat tugadi)")


def run_cycle(now: datetime | None = None) -> CycleStats:
    started = time.monotonic()
    now = now or timezone.now()
    stats = CycleStats()
    _resume_expired_pauses(now)
    _evaluate_states(now, stats)
    _notify_phase(now, stats)
    _refresh_suppressed(now)
    _reminders(now, stats)
    _close_incidents(now, stats)
    EvaluatorState.objects.update_or_create(
        pk=1,
        defaults={"last_run_at": now, "last_duration_ms": int((time.monotonic() - started) * 1000)},
    )
    return stats
