"""Alert tizimi (TZ 8.7, 6.7, 12): qoidalar, holat mashinasi (alert instance), incident, silence, maintenance."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.core.ids import uuid7
from apps.notifications.models import SEVERITIES

SEVERITY_CHOICES = [(s, s) for s in SEVERITIES]


class AlertRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    key = models.CharField(max_length=20, unique=True)  # 'AL-003'
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    scope = models.JSONField(
        default=dict
    )  # {"type": "host"|"job"|"channel"|"system", "tags": [...]}
    condition = models.JSONField()  # TZ 12.3 sxemasi
    for_seconds = models.PositiveIntegerField(default=0)
    resolve_after_seconds = models.PositiveIntegerField(default=60)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    channels = ArrayField(models.UUIDField(), default=list, blank=True)  # bo'sh = standart kanallar
    runbook_key = models.CharField(max_length=10, blank=True, default="")  # 'RB-004'
    runbook_hint = models.CharField(
        max_length=200, blank=True, default=""
    )  # xabarda "Nima qilish kerak"
    enabled = models.BooleanField(default=True)
    built_in = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(severity__in=list(SEVERITIES)), name="alert_rule_severity_valid"
            )
        ]

    def __str__(self) -> str:
        return f"{self.key} {self.name}"


class Incident(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        ACKNOWLEDGED = "acknowledged"
        RESOLVED = "resolved"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    scope_key = models.CharField(
        max_length=80
    )  # 'host:<server_id>' | 'job:<id>' | 'channel:<id>' | 'system'
    title = models.CharField(max_length=200)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=12, choices=Status, default=Status.OPEN)
    started_at = models.DateTimeField(default=timezone.now)
    acked_at = models.DateTimeField(null=True, blank=True)
    acked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    suppressed = models.BooleanField(
        default=False
    )  # barcha faol alertlar silence/maintenance ichida
    root_cause = models.TextField(blank=True, default="")
    summary = models.JSONField(default=dict, blank=True)
    # Takroriy eslatmalar uchun (12.4.1)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    reminders_sent = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope_key"],
                condition=~models.Q(status="resolved"),
                name="incidents_one_open_per_scope",
            ),
            models.CheckConstraint(
                condition=models.Q(severity__in=list(SEVERITIES)), name="incident_severity_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["open", "acknowledged", "resolved"]),
                name="incident_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["-started_at"], name="incidents_time_idx")]

    def __str__(self) -> str:
        return f"{self.scope_key}: {self.title} ({self.status})"


class AlertInstance(models.Model):
    class State(models.TextChoices):
        OK = "ok"
        PENDING = "pending"
        FIRING = "firing"
        RESOLVING = "resolving"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="instances")
    subject_type = models.CharField(max_length=12)  # host, job, channel, system
    subject_id = models.CharField(max_length=120)
    subject_name = models.CharField(
        max_length=160, blank=True, default=""
    )  # xabar uchun: 'main-2 (/)'
    fingerprint = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=10, choices=State, default=State.OK)
    pending_since = models.DateTimeField(null=True, blank=True)
    firing_since = models.DateTimeField(null=True, blank=True)
    resolving_since = models.DateTimeField(null=True, blank=True)
    last_eval_at = models.DateTimeField(default=timezone.now)
    last_value = models.FloatField(null=True, blank=True)
    detail = models.CharField(max_length=300, blank=True, default="")
    labels = models.JSONField(default=dict, blank=True)
    incident = models.ForeignKey(
        Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    suppressed = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state__in=["ok", "pending", "firing", "resolving"]),
                name="alert_instance_state_valid",
            )
        ]
        indexes = [
            models.Index(
                fields=["state"], condition=~models.Q(state="ok"), name="alert_instances_state_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.rule_id}/{self.subject_name or self.subject_id}: {self.state}"


class IncidentEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    time = models.DateTimeField(default=timezone.now)
    type = models.CharField(
        max_length=20
    )  # opened, alert_added, alert_resolved, acked, comment, notified, reminder, resolved, severity_changed
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["incident", "time"], name="incident_events_idx")]

    def __str__(self) -> str:
        return f"{self.incident_id} {self.type}"


class Silence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    matchers = models.JSONField()  # [{"label": "server", "op": "=", "value": "main-2"}, ...]
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=300)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")), name="silence_range_valid"
            ),
            models.CheckConstraint(condition=~models.Q(reason=""), name="silence_reason_required"),
        ]

    def __str__(self) -> str:
        return f"silence {self.id} -> {self.ends_at:%Y-%m-%d %H:%M}"


class MaintenanceWindow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    scope = models.JSONField()  # {"servers": [id...], "projects": [id...]}
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=300)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="maintenance_range_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"maintenance {self.id} {self.starts_at:%Y-%m-%d %H:%M}"


class EvaluatorState(models.Model):
    """Yagona qator: dvigatel ishlayotganini bildiradi (AL-084 uchun `evaluator_heartbeat`)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_run_at = models.DateTimeField(default=timezone.now)
    last_duration_ms = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"evaluator @ {self.last_run_at:%H:%M:%S}"
