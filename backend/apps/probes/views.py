"""Faol tekshiruvlar API (TZ 9.6)."""

from typing import Any

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
from .models import Probe

WRITERS: list[type[BasePermission]] = [IsAuthenticated, roles("owner", "operator")]
OWNER: list[type[BasePermission]] = [IsAuthenticated, roles("owner")]
MAX_RESULTS = 500


class ProbeSerializer(serializers.ModelSerializer[Probe]):
    last_result = serializers.SerializerMethodField()

    class Meta:
        model = Probe
        fields = [
            "id", "project", "domain", "type", "name", "config", "interval_s", "timeout_s", "enabled", "state",
            "state_since", "consecutive_failures", "last_run_at", "next_run_at", "created_at", "last_result",
        ]  # fmt: skip
        read_only_fields = [
            "id",
            "state",
            "state_since",
            "consecutive_failures",
            "last_run_at",
            "next_run_at",
            "created_at",
        ]

    def get_last_result(self, obj: Probe) -> dict[str, Any] | None:
        rows = services.recent_results(obj.pk, None, None, 1)
        return rows[0] if rows else None

    def validate_interval_s(self, value: int) -> int:
        if not 10 <= value <= 86400:
            raise serializers.ValidationError("10..86400 soniya bo'lishi kerak.")
        return value

    def validate_timeout_s(self, value: int) -> int:
        if not 1 <= value <= 60:
            raise serializers.ValidationError("1..60 soniya bo'lishi kerak.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind = attrs.get("type") or (self.instance.type if self.instance else None)
        if "config" in attrs or self.instance is None:
            try:
                services.validate_config(str(kind), attrs.get("config"))
            except services.ProbeConfigError as exc:
                raise serializers.ValidationError({"config": str(exc)}) from None
        if self.instance is not None and "type" in attrs and attrs["type"] != self.instance.type:
            raise serializers.ValidationError({"type": "Tekshiruv turini o'zgartirib bo'lmaydi."})
        interval = attrs.get("interval_s", self.instance.interval_s if self.instance else 60)
        timeout = attrs.get("timeout_s", self.instance.timeout_s if self.instance else 10)
        if timeout > interval:
            raise serializers.ValidationError(
                {"timeout_s": "timeout_s interval_s dan katta bo'lmasligi kerak."}
            )
        return attrs


def _private_allowed(request: Request, config: Any) -> bool:
    """`allow_private` (ichki manzillarga ruxsat, SSRF) — faqat Owner."""
    wants = isinstance(config, dict) and config.get("allow_private") is True
    return not wants or getattr(request.user, "role", "") == "owner"


class ProbeListView(APIView):
    def get_permissions(self) -> list[Any]:
        return [p() for p in (WRITERS if self.request.method == "POST" else [IsAuthenticated])]

    def get(self, request: Request) -> Response:
        q = request.query_params
        rows = Probe.objects.all().order_by("name")
        for field in ("type", "state", "project_id"):
            if value := q.get(field):
                rows = rows.filter(**{field: value})
        if q.get("enabled") in ("true", "false"):
            rows = rows.filter(enabled=q["enabled"] == "true")
        return Response({"items": ProbeSerializer(rows, many=True).data})

    def post(self, request: Request) -> HttpResponse:
        serializer = ProbeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not _private_allowed(request, serializer.validated_data.get("config")):
            return error_response("forbidden", "allow_private faqat Owner uchun.", 403)
        probe = serializer.save()
        record(
            "probe.create",
            request=request._request,
            object_type="probe",
            object_id=probe.pk,
            after=ProbeSerializer(probe).data,
        )
        return Response(ProbeSerializer(probe).data, status=201)


class ProbeDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        perms: list[type[BasePermission]] = {"PATCH": WRITERS, "DELETE": OWNER}.get(
            self.request.method or "", [IsAuthenticated]
        )
        return [p() for p in perms]

    def get(self, request: Request, pk: str) -> HttpResponse:
        probe = Probe.objects.filter(pk=pk).first()
        return (
            Response(ProbeSerializer(probe).data)
            if probe
            else error_response("not_found", "Tekshiruv topilmadi.", 404)
        )

    def patch(self, request: Request, pk: str) -> HttpResponse:
        probe = Probe.objects.filter(pk=pk).first()
        if probe is None:
            return error_response("not_found", "Tekshiruv topilmadi.", 404)
        before = ProbeSerializer(probe).data
        serializer = ProbeSerializer(probe, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if not _private_allowed(request, serializer.validated_data.get("config")):
            return error_response("forbidden", "allow_private faqat Owner uchun.", 403)
        serializer.save()
        if serializer.validated_data.get("enabled") is True and probe.state == Probe.State.PAUSED:
            probe.state, probe.next_run_at = Probe.State.UNKNOWN, timezone.now()
            probe.save(update_fields=["state", "next_run_at"])
        record(
            "probe.update",
            request=request._request,
            object_type="probe",
            object_id=probe.pk,
            before=before,
            after=serializer.data,
        )
        return Response(ProbeSerializer(probe).data)

    def delete(self, request: Request, pk: str) -> HttpResponse:
        """O'chirilmaydi: o'chirib qo'yiladi va `paused` bo'ladi (tarix saqlanadi)."""
        probe = Probe.objects.filter(pk=pk).first()
        if probe is None:
            return error_response("not_found", "Tekshiruv topilmadi.", 404)
        probe.enabled, probe.state = False, Probe.State.PAUSED
        probe.save(update_fields=["enabled", "state"])
        record("probe.archive", request=request._request, object_type="probe", object_id=probe.pk)
        return HttpResponse(status=204)


class ProbeRunView(APIView):
    permission_classes = WRITERS

    def post(self, request: Request, pk: str) -> HttpResponse:
        probe = Probe.objects.filter(pk=pk).first()
        if probe is None:
            return error_response("not_found", "Tekshiruv topilmadi.", 404)
        outcome = services.run_now(probe)
        return Response(
            {
                "ok": outcome.ok, "status_code": outcome.status_code, "total_ms": outcome.total_ms,
                "error_kind": outcome.error_kind, "detail": outcome.detail, "state": probe.state,
            }
        )  # fmt: skip


class ProbeResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> HttpResponse:
        if not Probe.objects.filter(pk=pk).exists():
            return error_response("not_found", "Tekshiruv topilmadi.", 404)
        q = request.query_params
        bounds = {}
        for key in ("from", "to"):
            if key in q:
                parsed = parse_datetime(q[key])
                if parsed is None:
                    return error_response(
                        "validation_error", f"{key} ISO-8601 bo'lishi kerak.", 400
                    )
                bounds[key] = parsed
        limit = q.get("limit", "100")
        if not limit.isdigit() or not 1 <= int(limit) <= MAX_RESULTS:
            return error_response(
                "validation_error", f"limit 1..{MAX_RESULTS} bo'lishi kerak.", 400
            )
        return Response(
            {"items": services.recent_results(pk, bounds.get("from"), bounds.get("to"), int(limit))}
        )


class ProbeUptimeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> HttpResponse:
        if not Probe.objects.filter(pk=pk).exists():
            return error_response("not_found", "Tekshiruv topilmadi.", 404)
        return Response(services.uptime(pk))


class CertListView(APIView):
    """`GET /certs/`: barcha sertifikatlar va qolgan kun (FR-TLS-003). `?days_left_lt=21`, `?project_id=`."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        from .models import CertStatus

        q = request.query_params
        rows = CertStatus.objects.select_related("domain__project").order_by("not_after")
        if project_id := q.get("project_id"):
            rows = rows.filter(domain__project_id=project_id)
        now = timezone.now()
        items = []
        for c in rows:
            days_left = int((c.not_after - now).total_seconds() // 86400)
            if "days_left_lt" in q and not (
                q["days_left_lt"].lstrip("-").isdigit() and days_left < int(q["days_left_lt"])
            ):
                continue
            items.append(
                {
                    "id": c.pk, "name": c.name, "source": c.source, "domain": str(c.domain_id) if c.domain_id else None,
                    "project": c.domain.project.slug if c.domain and c.domain.project else None,
                    "not_after": c.not_after, "days_left": days_left, "issuer": c.issuer, "subject": c.subject,
                    "san": c.san, "chain_ok": c.chain_ok, "hostname_ok": c.hostname_ok, "checked_at": c.checked_at,
                }
            )  # fmt: skip
        if "days_left_lt" in q and not q["days_left_lt"].lstrip("-").isdigit():
            return error_response("validation_error", "days_left_lt butun son bo'lishi kerak.", 400)
        return Response({"items": items})


class DomainDnsView(APIView):
    """`GET /domains/{id}/dns`: resolverlar bo'yicha oxirgi natija va o'zgarishlar tarixi (FR-DNS-002, FR-DNS-008)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> HttpResponse:
        from django.db import connection

        from apps.registry.models import Domain

        from .models import DnsChange

        if not Domain.objects.filter(pk=pk).exists():
            return error_response("not_found", "Domen topilmadi.", 404)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (resolver) resolver, rtype, time, answers, matches, rcode, latency_ms
                FROM dns_results WHERE domain_id = %s ORDER BY resolver, time DESC
                """,
                [pk],
            )
            cols = [c.name for c in cursor.description or []]
            latest = [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]
        changes = DnsChange.objects.filter(domain_id=pk).order_by("-changed_at")[:50]
        return Response(
            {
                "resolvers": latest,
                "changes": [
                    {
                        "resolver": c.resolver,
                        "rtype": c.rtype,
                        "old_answers": c.old_answers,
                        "new_answers": c.new_answers,
                        "changed_at": c.changed_at,
                    }
                    for c in changes
                ],
            }
        )
