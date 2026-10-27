"""Alert xabarlari (TZ 12.9): ahamiyat belgisi + sarlavha, qayerda, nima, qachondan, ta'sir, nima qilish kerak."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apps.notifications.messages import Message
from apps.registry.models import ProjectServer

from .models import AlertInstance, Incident

LOCAL_TZ = ZoneInfo("Asia/Tashkent")  # FR-NTF-003: vaqt mahalliy zonada
MAX_LISTED = 5


def human_duration(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 90:
        return f"{max(seconds, 0)} soniya"
    minutes = round(seconds / 60)
    if minutes < 90:
        return f"{minutes} daqiqa"
    hours, rem = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} soat {rem} daqiqa" if rem else f"{hours} soat"
    return f"{hours // 24} kun {hours % 24} soat"


def local_time(dt: datetime) -> str:
    return dt.astimezone(LOCAL_TZ).strftime("%H:%M")


def affected_projects(server_id: str) -> list[str]:
    rows = ProjectServer.objects.filter(server_id=server_id).select_related("project")
    return sorted({r.project.name for r in rows if r.project.status == "active"})


def alert_title(instance: AlertInstance) -> str:
    return (
        f"{instance.rule.name}: {instance.subject_name}"
        if instance.subject_name
        else instance.rule.name
    )


def alert_message(instance: AlertInstance, *, joined: bool = False) -> Message:
    """Bitta alert uchun xabar. `joined` — incident allaqachon ochiq edi (qo'shimcha alert)."""
    rule = instance.rule
    lines = [instance.detail] if instance.detail else []
    onset = instance.pending_since or instance.firing_since
    if onset:
        lines.append(f"Qachondan: {local_time(onset)} (Asia/Tashkent)")
    if instance.subject_type == "host":
        server_id = instance.subject_id.split(":")[0]
        projects = affected_projects(server_id)
        if projects:
            lines.append(f"Ta'sirlangan loyihalar ({len(projects)}): {', '.join(projects[:10])}")
    hint = f"{rule.runbook_key} → {rule.runbook_hint}" if rule.runbook_hint else rule.runbook_key
    title = alert_title(instance)
    if joined and instance.incident is not None:
        others = [
            alert_title(a)
            for a in instance.incident.alerts.filter(state=AlertInstance.State.FIRING)
            .exclude(pk=instance.pk)
            .select_related("rule")
        ]
        if others:
            lines.append(f"Shu incidentdagi boshqa faol alertlar: {'; '.join(others[:MAX_LISTED])}")
    return Message(
        severity=rule.severity,
        title=title,
        lines=lines,
        runbook=hint,
        path=f"/incidents/{instance.incident_id}" if instance.incident_id else "",
    )


def reminder_message(incident: Incident, active: list[AlertInstance], now: datetime) -> Message:
    lines = [f"Hali hal bo'lmagan, ochiq: {human_duration(now - incident.started_at)}"]
    for inst in active[:MAX_LISTED]:
        lines.append(f"• {alert_title(inst)}" + (f" — {inst.detail}" if inst.detail else ""))
    if len(active) > MAX_LISTED:
        lines.append(f"+{len(active) - MAX_LISTED} ta")
    lines.append("Qabul qilinmagan (eslatma ack bo'lguncha takrorlanadi).")
    return Message(
        severity=incident.severity,
        title=f"Eslatma: {incident.title}",
        lines=lines,
        path=f"/incidents/{incident.pk}",
    )


def resolved_message(incident: Incident, ended: datetime) -> Message:
    duration = human_duration(ended - incident.started_at)
    return Message(
        severity=incident.severity,
        title=f"Tiklandi: {incident.title}",
        lines=[
            f"Davomiyligi: {duration} ({local_time(incident.started_at)} – {local_time(ended)})",
            "Sabab: (kiritilmagan) ← panelda izoh qo'shing",
        ],
        resolved=True,
        path=f"/incidents/{incident.pk}",
    )
