"""Alertlar va incidentlar API (TZ 9.8): qoidalar, incidentlar, silence, maintenance."""

import secrets
from typing import Any

from django.db.models import QuerySet
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.http import error_response
from apps.core.permissions import roles

from . import services
from .conditions import Ctx, evaluate_rule
from .models import AlertInstance, AlertRule, Incident, MaintenanceWindow, Silence
from .serializers import (
    AlertInstanceSerializer,
    AlertRuleSerializer,
    IncidentEventSerializer,
    IncidentSerializer,
    MaintenanceSerializer,
    SilenceSerializer,
)

PAGE_SIZE = 50
WRITERS: list[type[BasePermission]] = [IsAuthenticated, roles("owner", "operator")]


def _not_found(what: str) -> HttpResponse:
    return error_response("not_found", f"{what} topilmadi.", 404)


# ----------------------------------------------------------------------- qoidalar
class RuleListView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "POST" else [IsAuthenticated])]

    def get(self, request: Request) -> Response:
        rules = AlertRule.objects.order_by("key")
        for param, field in (("enabled", "enabled"), ("built_in", "built_in")):
            if (value := request.query_params.get(param)) in ("true", "false"):
                rules = rules.filter(**{field: value == "true"})
        if severity := request.query_params.get("severity"):
            rules = rules.filter(severity=severity)
        return Response({"items": AlertRuleSerializer(rules, many=True).data})

    def post(self, request: Request) -> HttpResponse:
        serializer = AlertRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = "USR-" + secrets.token_hex(3).upper()
        rule = AlertRule.objects.create(key=key, built_in=False, **serializer.validated_data)
        record(
            "rule.create",
            request=request._request,
            object_type="alert_rule",
            object_id=rule.pk,
            after=AlertRuleSerializer(rule).data,
        )
        return Response(AlertRuleSerializer(rule).data, status=201)


class RuleDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "PATCH" else [IsAuthenticated])]

    def get(self, request: Request, pk: str) -> HttpResponse:
        rule = AlertRule.objects.filter(pk=pk).first()
        return Response(AlertRuleSerializer(rule).data) if rule else _not_found("Qoida")

    def patch(self, request: Request, pk: str) -> HttpResponse:
        rule = AlertRule.objects.filter(pk=pk).first()
        if rule is None:
            return _not_found("Qoida")
        before = AlertRuleSerializer(rule).data
        serializer = AlertRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record(
            "rule.update",
            request=request._request,
            object_type="alert_rule",
            object_id=rule.pk,
            before=before,
            after=serializer.data,
        )
        return Response(serializer.data)


class RuleTestView(APIView):
    """Quruq hisoblash (FR-ALR-... 12.8): hozir kim 'firing' bo'lardi; holat va bildirishnomaga tegmaydi.
    `for` ni hisobga olmaydi: faqat shart hozir rostmi."""

    permission_classes = WRITERS

    def post(self, request: Request, pk: str) -> HttpResponse:
        rule = AlertRule.objects.filter(pk=pk).first()
        if rule is None:
            return _not_found("Qoida")
        subjects = evaluate_rule(rule, Ctx(timezone.now()))
        items = [
            {"subject": s.name, "firing": s.firing, "value": s.value, "detail": s.detail}
            for s in subjects
        ]
        return Response({"firing_count": sum(1 for s in subjects if s.firing), "items": items})


class AlertListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        active = (
            AlertInstance.objects.exclude(state=AlertInstance.State.OK)
            .select_related("rule")
            .order_by("-firing_since")
        )
        return Response({"items": AlertInstanceSerializer(active, many=True).data})


# ----------------------------------------------------------------------- incidentlar
class IncidentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        rows = Incident.objects.order_by("-started_at", "-id")
        q = request.query_params
        if status := q.get("filter[status]") or q.get("status"):
            rows = rows.filter(status=status)
        if severity := q.get("severity"):
            rows = rows.filter(severity=severity)
        if server_id := q.get("server_id"):
            rows = rows.filter(scope_key=f"host:{server_id}")
        for param, lookup in (
            ("from", "started_at__gte"),
            ("to", "started_at__lte"),
            ("before", "started_at__lt"),
        ):
            if param in q:
                parsed = parse_datetime(q[param])
                if parsed is None:
                    return error_response(
                        "validation_error", f"{param} ISO-8601 bo'lishi kerak.", 400
                    )
                rows = rows.filter(**{lookup: parsed})
        page = list(rows[: PAGE_SIZE + 1])
        more = len(page) > PAGE_SIZE
        page = page[:PAGE_SIZE]
        return Response(
            {
                "items": IncidentSerializer(page, many=True).data,
                "next_before": page[-1].started_at.isoformat().replace("+00:00", "Z")
                if more
                else None,
            }
        )


class IncidentDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "PATCH" else [IsAuthenticated])]

    def get(self, request: Request, pk: str) -> HttpResponse:
        incident = Incident.objects.filter(pk=pk).first()
        if incident is None:
            return _not_found("Incident")
        alerts = incident.alerts.select_related("rule").order_by("-firing_since")
        return Response(
            {
                **IncidentSerializer(incident).data,
                "alerts": AlertInstanceSerializer(alerts, many=True).data,
                "events": IncidentEventSerializer(
                    incident.events.select_related("user").order_by("time", "id"), many=True
                ).data,
            }
        )

    def patch(self, request: Request, pk: str) -> HttpResponse:
        incident = Incident.objects.filter(pk=pk).first()
        if incident is None:
            return _not_found("Incident")
        cause = request.data.get("root_cause") if isinstance(request.data, dict) else None
        if not isinstance(cause, str) or len(cause) > 2000:
            raise serializers.ValidationError({"root_cause": "Matn (≤ 2000 belgi) bo'lishi kerak."})
        before = incident.root_cause
        incident.root_cause = cause
        incident.save(update_fields=["root_cause"])
        record(
            "incident.root_cause",
            request=request._request,
            object_type="incident",
            object_id=incident.pk,
            before={"root_cause": before},
            after={"root_cause": cause},
        )
        return Response(IncidentSerializer(incident).data)


class IncidentActionView(APIView):
    """ack / comments / resolve uchun umumiy asos."""

    permission_classes = WRITERS

    def run(self, request: Request, incident: Incident) -> Response:
        raise NotImplementedError

    def post(self, request: Request, pk: str) -> HttpResponse:
        incident = Incident.objects.filter(pk=pk).first()
        if incident is None:
            return _not_found("Incident")
        try:
            return self.run(request, incident)
        except services.IncidentConflict as exc:
            return error_response("conflict", str(exc), 409)


def _body(request: Request) -> dict[str, Any]:
    return request.data if isinstance(request.data, dict) else {}


class IncidentAckView(IncidentActionView):
    def run(self, request: Request, incident: Incident) -> Response:
        text = _body(request).get("comment", "")
        if not isinstance(text, str) or len(text) > 500:
            raise serializers.ValidationError({"comment": "Matn (≤ 500 belgi) bo'lishi kerak."})
        services.ack(incident, request.user, text)
        record(
            "incident.ack", request=request._request, object_type="incident", object_id=incident.pk
        )
        return Response(IncidentSerializer(incident).data)


class IncidentCommentView(IncidentActionView):
    def run(self, request: Request, incident: Incident) -> Response:
        text = _body(request).get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise serializers.ValidationError({"text": "Matn (1..2000 belgi) majburiy."})
        event = services.comment(incident, request.user, text.strip())
        return Response(IncidentEventSerializer(event).data, status=201)


class IncidentResolveView(IncidentActionView):
    def run(self, request: Request, incident: Incident) -> Response:
        services.resolve_manually(incident, request.user)
        record(
            "incident.resolve",
            request=request._request,
            object_type="incident",
            object_id=incident.pk,
        )
        return Response(IncidentSerializer(incident).data)


# ----------------------------------------------------------------------- silence va maintenance
class _CancellableList(APIView):
    """GET (hamma) / POST (owner, operator) / DELETE bekor qilish (owner, operator)."""

    model: Any
    serializer: Any
    action: str
    kind: str

    def get_permissions(self) -> list[Any]:
        return [
            p()
            for p in (WRITERS if self.request.method in ("POST", "DELETE") else [IsAuthenticated])
        ]

    def queryset(self, request: Request) -> QuerySet[Any]:
        rows: QuerySet[Any] = self.model.objects.order_by("-ends_at")
        if request.query_params.get("all") != "1":
            rows = rows.filter(cancelled_at__isnull=True, ends_at__gt=timezone.now())
        return rows

    def get(self, request: Request) -> Response:
        return Response({"items": self.serializer(self.queryset(request), many=True).data})

    def post(self, request: Request) -> HttpResponse:
        s = self.serializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = self.model.objects.create(created_by=request.user, **s.validated_data)
        record(
            f"{self.action}.create",
            request=request._request,
            object_type=self.kind,
            object_id=obj.pk,
            after=self.serializer(obj).data,
        )
        return Response(self.serializer(obj).data, status=201)


class _CancelView(APIView):
    permission_classes = WRITERS
    model: Any
    action: str
    kind: str

    def delete(self, request: Request, pk: str) -> HttpResponse:
        obj = self.model.objects.filter(pk=pk, cancelled_at__isnull=True).first()
        if obj is None:
            return _not_found("Yozuv")
        obj.cancelled_at = timezone.now()
        obj.save(update_fields=["cancelled_at"])
        record(
            f"{self.action}.cancel",
            request=request._request,
            object_type=self.kind,
            object_id=obj.pk,
        )
        return HttpResponse(status=204)


class SilenceListView(_CancellableList):
    model, serializer, action, kind = Silence, SilenceSerializer, "silence", "silence"


class SilenceCancelView(_CancelView):
    model, action, kind = Silence, "silence", "silence"


class MaintenanceListView(_CancellableList):
    model, serializer, action, kind = (
        MaintenanceWindow,
        MaintenanceSerializer,
        "maintenance",
        "maintenance",
    )


class MaintenanceCancelView(_CancelView):
    model, action, kind = MaintenanceWindow, "maintenance", "maintenance"
