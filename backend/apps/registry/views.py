"""Serverlar (TZ 9.3): ro'yxat, yaratish (enroll token bilan), enroll token yangilash.

To'liq CRUD (PATCH, pauza, arxiv) B2 da.
"""

from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
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
        servers = Server.objects.exclude(status=Server.Status.ARCHIVED).order_by("name")
        return Response({"items": ServerSerializer(servers, many=True).data})

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


class ServerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> HttpResponse:
        server = Server.objects.filter(pk=pk).first()
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        return Response(ServerSerializer(server).data)


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
