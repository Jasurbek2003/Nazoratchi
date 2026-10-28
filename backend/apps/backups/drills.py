"""Restore drill API (TZ 9.7, 10.8): natijani kiritish va tuzatish, tarix."""

from datetime import datetime, timedelta
from typing import Any

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.http import error_response
from apps.core.permissions import roles
from apps.registry.models import Project

from .models import RestoreDrill

PAGE_SIZE = 50
DEFAULT_DRILL_EVERY_DAYS = 90


class DrillSerializer(serializers.ModelSerializer[RestoreDrill]):
    project = serializers.SlugRelatedField(slug_field="slug", queryset=Project.objects.all())
    performed_by = serializers.SerializerMethodField()

    class Meta:
        model = RestoreDrill
        fields = [
            "id", "project", "performed_at", "performed_by", "backup_file", "backup_age_h",
            "duration_s", "tables_count", "rows_count", "result", "notes",
        ]  # fmt: skip
        read_only_fields = ["id"]

    def get_performed_by(self, obj: RestoreDrill) -> str | None:
        return obj.performed_by.login if obj.performed_by else None

    def validate_performed_at(self, value: datetime) -> datetime:
        if value > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("Kelajak sanasini kiritib bo'lmaydi.")
        return value

    def validate_backup_file(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Zaxira fayli nomi kerak.")
        return value

    def validate_notes(self, value: str) -> str:
        if len(value) > 2000:
            raise serializers.ValidationError("Izoh 2000 belgidan oshmasin.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is not None and "project" in attrs:
            raise serializers.ValidationError({"project": "Loyihani o'zgartirib bo'lmaydi."})
        return attrs


def drill_summary(
    project: Project,
    last: RestoreDrill | None,
    last_ok: RestoreDrill | None,
    now: datetime,
) -> dict[str, Any]:
    """Kartadagi blok: oxirgi drill va muddat (R-117: "hech qachon" aniq ko'rinsin)."""
    every = int((project.backup or {}).get("drill_every_days") or DEFAULT_DRILL_EVERY_DAYS)
    ok_days = (now - last_ok.performed_at).days if last_ok else None
    return {
        "every_days": every,
        "last": DrillSerializer(last).data if last else None,
        "last_success_days": ok_days,
        "never": last_ok is None,
        "overdue": ok_days is None or ok_days > every,
    }


def _writer_perms(request: Request, method: str) -> list[Any]:
    perms: list[type[BasePermission]] = (
        [IsAuthenticated, roles("owner", "operator")]
        if request.method == method
        else [IsAuthenticated]
    )
    return [p() for p in perms]


class DrillListView(APIView):
    def get_permissions(self) -> list[Any]:
        return _writer_perms(self.request, "POST")

    def get(self, request: Request) -> Response:
        qs = RestoreDrill.objects.select_related("project", "performed_by").order_by(
            "-performed_at"
        )
        if slug := request.query_params.get("project"):
            qs = qs.filter(project__slug=slug)
        if result := request.query_params.get("result"):
            qs = qs.filter(result=result)
        return Response({"items": DrillSerializer(qs[:PAGE_SIZE], many=True).data})

    def post(self, request: Request) -> HttpResponse:
        serializer = DrillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        drill = serializer.save(performed_by=request.user)
        data = DrillSerializer(drill).data
        record(
            "drill.create",
            request=request._request,
            object_type="restore_drill",
            object_id=drill.pk,
            after=data,
        )
        return Response(data, status=201)


class DrillDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        return _writer_perms(self.request, "PATCH")

    def get(self, request: Request, pk: str) -> HttpResponse:
        drill = RestoreDrill.objects.filter(pk=pk).first()
        if drill is None:
            return error_response("not_found", "Drill topilmadi.", 404)
        return Response(DrillSerializer(drill).data)

    def patch(self, request: Request, pk: str) -> HttpResponse:
        drill = RestoreDrill.objects.filter(pk=pk).first()
        if drill is None:
            return error_response("not_found", "Drill topilmadi.", 404)
        before = DrillSerializer(drill).data
        serializer = DrillSerializer(drill, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        data = DrillSerializer(drill).data
        record(
            "drill.update",
            request=request._request,
            object_type="restore_drill",
            object_id=drill.pk,
            before=before,
            after=data,
        )
        return Response(data)
