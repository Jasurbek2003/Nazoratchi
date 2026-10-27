from datetime import timedelta
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.notifications.models import SEVERITIES

from .conditions import ConditionError, validate_condition
from .models import AlertInstance, AlertRule, Incident, IncidentEvent, MaintenanceWindow, Silence
from .suppression import MatcherError, validate_matchers

MIN_SILENCE = timedelta(minutes=15)
MAX_SILENCE = timedelta(days=30)
SCOPE_TYPES = {"host", "job", "channel", "system"}


class AlertRuleSerializer(serializers.ModelSerializer[AlertRule]):
    class Meta:
        model = AlertRule
        fields = [
            "id", "key", "name", "description", "scope", "condition", "for_seconds", "resolve_after_seconds",
            "severity", "channels", "runbook_key", "runbook_hint", "enabled", "built_in", "updated_at",
        ]  # fmt: skip
        read_only_fields = ["id", "key", "built_in", "updated_at"]

    def validate_severity(self, value: str) -> str:
        if value not in SEVERITIES:
            raise serializers.ValidationError(f"{', '.join(SEVERITIES)} dan biri bo'lishi kerak.")
        return value

    def validate_condition(self, value: Any) -> Any:
        try:
            validate_condition(value)
        except ConditionError as exc:
            raise serializers.ValidationError(str(exc)) from None
        return value

    def validate_scope(self, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("type") not in SCOPE_TYPES:
            raise serializers.ValidationError(
                f"scope.type {', '.join(sorted(SCOPE_TYPES))} dan biri bo'lishi kerak."
            )
        return value

    def validate_for_seconds(self, value: int) -> int:
        if value > 7 * 86400:
            raise serializers.ValidationError("for_seconds 7 kundan oshmasligi kerak.")
        return value


class AlertInstanceSerializer(serializers.ModelSerializer[AlertInstance]):
    rule_key = serializers.CharField(source="rule.key", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    severity = serializers.CharField(source="rule.severity", read_only=True)

    class Meta:
        model = AlertInstance
        fields = [
            "id", "rule", "rule_key", "rule_name", "severity", "subject_type", "subject_id", "subject_name",
            "state", "pending_since", "firing_since", "resolving_since", "last_eval_at", "last_value",
            "detail", "incident", "suppressed", "notified_at",
        ]  # fmt: skip


class IncidentEventSerializer(serializers.ModelSerializer[IncidentEvent]):
    user = serializers.CharField(source="user.login", read_only=True, default=None)

    class Meta:
        model = IncidentEvent
        fields = ["id", "time", "type", "user", "data"]


class IncidentSerializer(serializers.ModelSerializer[Incident]):
    acked_by = serializers.CharField(source="acked_by.login", read_only=True, default=None)

    class Meta:
        model = Incident
        fields = [
            "id", "scope_key", "title", "severity", "status", "started_at", "acked_at", "acked_by",
            "resolved_at", "suppressed", "root_cause", "summary",
        ]  # fmt: skip


class SilenceSerializer(serializers.ModelSerializer[Silence]):
    created_by = serializers.CharField(source="created_by.login", read_only=True, default=None)

    class Meta:
        model = Silence
        fields = [
            "id",
            "matchers",
            "starts_at",
            "ends_at",
            "reason",
            "created_by",
            "created_at",
            "cancelled_at",
        ]
        read_only_fields = ["id", "starts_at", "created_by", "created_at", "cancelled_at"]

    def validate_matchers(self, value: Any) -> Any:
        try:
            validate_matchers(value)
        except MatcherError as exc:
            raise serializers.ValidationError(str(exc)) from None
        return value

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Sabab majburiy.")
        return value.strip()

    def validate_ends_at(self, value: Any) -> Any:
        span = value - timezone.now()
        if not MIN_SILENCE <= span <= MAX_SILENCE + timedelta(minutes=1):
            raise serializers.ValidationError("Muddat 15 daqiqadan 30 kungacha bo'lishi kerak.")
        return value


class MaintenanceSerializer(serializers.ModelSerializer[MaintenanceWindow]):
    created_by = serializers.CharField(source="created_by.login", read_only=True, default=None)

    class Meta:
        model = MaintenanceWindow
        fields = ["id", "scope", "starts_at", "ends_at", "reason", "created_by", "cancelled_at"]
        read_only_fields = ["id", "created_by", "cancelled_at"]

    def validate_scope(self, value: Any) -> Any:
        ok = (
            isinstance(value, dict)
            and set(value) <= {"servers", "projects"}
            and any(isinstance(value.get(k), list) and value[k] for k in ("servers", "projects"))
        )
        if not ok or any(
            not isinstance(i, str) for k in ("servers", "projects") for i in value.get(k, [])
        ):
            raise serializers.ValidationError(
                "scope {'servers': [id...], 'projects': [id...]} bo'lishi va kamida bitta id bo'lishi kerak."
            )
        return value

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Sabab majburiy.")
        return value.strip()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError(
                {"ends_at": "Tugash vaqti boshlanishdan keyin bo'lishi kerak."}
            )
        if attrs["ends_at"] - attrs["starts_at"] > timedelta(days=30):
            raise serializers.ValidationError({"ends_at": "Oyna 30 kundan uzun bo'lmasligi kerak."})
        return attrs
