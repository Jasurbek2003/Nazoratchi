"""Incident ustidagi qo'lda amallar (FR-ALR-013/016): qabul qilish, izoh, qo'lda yopish."""

from typing import Any

from django.utils import timezone

from .models import AlertInstance, Incident, IncidentEvent


class IncidentConflict(Exception):
    """Amalni hozirgi holatda bajarib bo'lmaydi (409)."""


def ack(incident: Incident, user: Any, comment: str = "") -> Incident:
    if incident.status == Incident.Status.RESOLVED:
        raise IncidentConflict("Yopilgan incidentni qabul qilib bo'lmaydi.")
    if incident.status == Incident.Status.ACKNOWLEDGED:
        raise IncidentConflict("Incident allaqachon qabul qilingan.")
    now = timezone.now()
    incident.status, incident.acked_at, incident.acked_by = Incident.Status.ACKNOWLEDGED, now, user
    incident.save(update_fields=["status", "acked_at", "acked_by"])
    IncidentEvent.objects.create(
        incident=incident,
        type="acked",
        time=now,
        user=user,
        data={"comment": comment} if comment else {},
    )
    return incident


def comment(incident: Incident, user: Any, text: str) -> IncidentEvent:
    return IncidentEvent.objects.create(
        incident=incident, type="comment", user=user, data={"text": text}
    )


def resolve_manually(incident: Incident, user: Any) -> Incident:
    """Faqat shart allaqachon yo'qolgan bo'lsa (hamma alert `ok`/`pending`); aks holda 409 (TZ 9.x)."""
    if incident.status == Incident.Status.RESOLVED:
        raise IncidentConflict("Incident allaqachon yopilgan.")
    if incident.alerts.filter(
        state__in=[AlertInstance.State.FIRING, AlertInstance.State.RESOLVING]
    ).exists():
        raise IncidentConflict("Shart hamon rost: incident avtomatik yopilishini kuting.")
    now = timezone.now()
    incident.status, incident.resolved_at = Incident.Status.RESOLVED, now
    incident.save(update_fields=["status", "resolved_at"])
    IncidentEvent.objects.create(
        incident=incident, type="resolved", time=now, user=user, data={"manual": True}
    )
    return incident
