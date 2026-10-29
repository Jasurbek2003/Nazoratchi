"""Serverlar (TZ 9.3): ro'yxat, yaratish (enroll token bilan), enroll token yangilash.

To'liq CRUD (PATCH, pauza, arxiv) B2 da.
"""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.http import error_response
from apps.core.permissions import roles

from .models import EnrollToken, HostEvent, Server
from .serializers import ServerSerializer


def enroll_payload(token: str, row: EnrollToken) -> dict[str, Any]:
    return {
        "token": token,
        "expires_at": row.expires_at.isoformat().replace("+00:00", "Z"),
        # install.sh B5d da tayyor bo'ladi (agent o'rnatuvchi)
        "install_command": f"curl -fsSL {settings.PUBLIC_URL}/install.sh | sudo bash -s -- --token {token}",
    }


class ServerListView(APIView):
    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            return [IsAuthenticated(), roles("owner", "operator")()]
        return [IsAuthenticated()]

    def get(self, request: Request) -> Response:
        q = request.query_params
        archived = q.get("status") == Server.Status.ARCHIVED
        servers = (
            Server.objects.all()
            if archived
            else Server.objects.exclude(status=Server.Status.ARCHIVED)
        )
        if status := q.get("status"):
            servers = servers.filter(status=status)
        if tag := q.get("tag"):
            servers = servers.filter(tags__contains=[tag])
        if text := q.get("q"):
            servers = servers.filter(
                Q(name__icontains=text)
                | Q(provider__icontains=text)
                | Q(public_ipv4__startswith=text)
            )
        return Response({"items": ServerSerializer(servers.order_by("name"), many=True).data})

    def post(self, request: Request) -> HttpResponse:
        serializer = ServerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                server = Server.objects.create(**serializer.validated_data)
                row, token = EnrollToken.issue(server, created_by=request.user)
        except IntegrityError:
            return error_response("duplicate", "Bunday nomli server mavjud.", 409)
        record(
            "server.create",
            request=request._request,
            object_type="server",
            object_id=server.id,
            after=ServerSerializer(server).data,
        )
        return Response(
            {**ServerSerializer(server).data, "enroll": enroll_payload(token, row)}, status=201
        )


CLOCK_SKEW_FRESH = timedelta(minutes=5)


def _clock_skew(server: Server) -> float | None:
    """Agent o'lchagan soat farqi (core - agent, soniya). Yangi qiymat bo'lmasa None (eskirgan son yolg'on belgi beradi)."""
    from apps.metrics.models import SeriesLatest

    return (
        SeriesLatest.objects.filter(
            series__server=server,
            series__name="agent_clock_skew_seconds",
            time__gte=timezone.now() - CLOCK_SKEW_FRESH,
        )
        .values_list("value", flat=True)
        .first()
    )


class ServerDetailView(APIView):
    def get_permissions(self) -> list[Any]:
        classes: list[type[BasePermission]] = [IsAuthenticated]
        if self.request.method == "PATCH":
            classes.append(roles("owner", "operator"))
        return [p() for p in classes]

    def get(self, request: Request, pk: str) -> HttpResponse:
        from apps.alerts.models import Incident

        server = Server.objects.filter(pk=pk).first()
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        open_incidents = (
            Incident.objects.filter(scope_key=f"host:{server.pk}")
            .exclude(status="resolved")
            .count()
        )
        return Response(
            {
                **ServerSerializer(server).data,
                "open_incidents": open_incidents,
                "clock_skew_seconds": _clock_skew(server),
            }
        )

    def patch(self, request: Request, pk: str) -> HttpResponse:
        server = Server.objects.filter(pk=pk).exclude(status=Server.Status.ARCHIVED).first()
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        before = ServerSerializer(server).data
        serializer = ServerSerializer(server, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            return error_response("duplicate", "Bunday nomli server mavjud.", 409)
        record(
            "server.update",
            request=request._request,
            object_type="server",
            object_id=server.pk,
            before=before,
            after=serializer.data,
        )
        return Response(serializer.data)


class ServerEnrollTokenView(APIView):
    permission_classes = [IsAuthenticated, roles("owner")]

    def post(self, request: Request, pk: str) -> HttpResponse:
        server = Server.objects.filter(pk=pk).exclude(status=Server.Status.ARCHIVED).first()
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        row, token = EnrollToken.issue(server, created_by=request.user)
        HostEvent.objects.create(server=server, type="enroll_token_issued")
        record(
            "server.enroll_token",
            request=request._request,
            object_type="server",
            object_id=server.id,
        )
        return Response(enroll_payload(token, row), status=201)
