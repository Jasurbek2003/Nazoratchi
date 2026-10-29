"""Server amallari (TZ 9.3): pauza/davom, arxiv, voqealar, agent tokenlari."""

from datetime import timedelta
from typing import Any

from django.db import transaction
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

from . import agent_update
from .models import AgentToken, HostEvent, Server
from .serializers import ServerSerializer

WRITERS: list[type[BasePermission]] = [IsAuthenticated, roles("owner", "operator")]
OWNER: list[type[BasePermission]] = [IsAuthenticated, roles("owner")]
MAX_PAUSE = timedelta(days=90)
PAGE_SIZE = 50


def _server(pk: str) -> Server | None:
    return Server.objects.filter(pk=pk).exclude(status=Server.Status.ARCHIVED).first()


def _login(request: Request) -> str:
    return str(getattr(request.user, "login", ""))


def _body(request: Request) -> dict[str, Any]:
    return request.data if isinstance(request.data, dict) else {}


class ServerPauseView(APIView):
    """Pauza (FR-HST-016): alertlar bostiriladi, ma'lumot yig'ilaveradi. `until` bo'lsa o'zi davom etadi."""

    permission_classes = WRITERS

    def post(self, request: Request, pk: str) -> HttpResponse:
        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        if server.status == Server.Status.PAUSED:
            return error_response("conflict", "Server allaqachon pauzada.", 409)
        body = _body(request)
        reason = body.get("reason")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 200:
            raise serializers.ValidationError({"reason": "Sabab majburiy (≤ 200 belgi)."})
        until = None
        if body.get("until") is not None:
            until = parse_datetime(str(body["until"]))
            now = timezone.now()
            if until is None or not now < until <= now + MAX_PAUSE:
                raise serializers.ValidationError(
                    {"until": "Kelajakdagi ISO vaqt (≤ 90 kun) bo'lishi kerak."}
                )
        server.status, server.paused_at = Server.Status.PAUSED, timezone.now()
        server.paused_by = request.user  # type: ignore[assignment]
        server.paused_until, server.pause_reason = until, reason.strip()
        server.save(
            update_fields=["status", "paused_at", "paused_by", "paused_until", "pause_reason"]
        )
        HostEvent.objects.create(
            server=server,
            type="paused",
            data={"reason": server.pause_reason, "by": _login(request)},
        )
        record(
            "server.pause",
            request=request._request,
            object_type="server",
            object_id=server.pk,
            after={"reason": server.pause_reason},
        )
        return Response(ServerSerializer(server).data)


def resume(server: Server, by: str) -> None:
    """Pauzani tugatadi. Hech qachon ma'lumot yubormagan server `new` ga, qolgani `online` ga qaytadi."""
    server.status = Server.Status.ONLINE if server.last_seen_at else Server.Status.NEW
    server.paused_at = server.paused_until = None
    server.pause_reason = ""
    server.save(update_fields=["status", "paused_at", "paused_until", "pause_reason"])
    HostEvent.objects.create(server=server, type="resumed", data={"by": by})


class ServerResumeView(APIView):
    permission_classes = WRITERS

    def post(self, request: Request, pk: str) -> HttpResponse:
        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        if server.status != Server.Status.PAUSED:
            return error_response("conflict", "Server pauzada emas.", 409)
        resume(server, _login(request))
        record("server.resume", request=request._request, object_type="server", object_id=server.pk)
        return Response(ServerSerializer(server).data)


class ServerArchiveView(APIView):
    """Obyekt o'chirilmaydi, arxivga o'tadi (FR-REG-006): tarix saqlanadi, tokenlar bekor qilinadi, alert yo'q."""

    permission_classes = OWNER

    def post(self, request: Request, pk: str) -> HttpResponse:
        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        with transaction.atomic():
            server.status = Server.Status.ARCHIVED
            server.save(update_fields=["status"])
            revoked = AgentToken.objects.filter(server=server, revoked_at__isnull=True).update(
                revoked_at=timezone.now()
            )
            HostEvent.objects.create(
                server=server,
                type="archived",
                data={"by": _login(request), "tokens_revoked": revoked},
            )
        record(
            "server.archive", request=request._request, object_type="server", object_id=server.pk
        )
        return Response(ServerSerializer(server).data)


class ServerEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> HttpResponse:
        if not Server.objects.filter(pk=pk).exists():
            return error_response("not_found", "Server topilmadi.", 404)
        rows = HostEvent.objects.filter(server_id=pk).order_by("-id")
        before = request.query_params.get("before")
        if before:
            if not before.isdigit():
                return error_response("validation_error", "before butun son bo'lishi kerak.", 400)
            rows = rows.filter(id__lt=int(before))
        page = list(rows[: PAGE_SIZE + 1])
        more = len(page) > PAGE_SIZE
        page = page[:PAGE_SIZE]
        items = [{"id": e.id, "time": e.time, "type": e.type, "data": e.data} for e in page]
        return Response({"items": items, "next_before": page[-1].id if more else None})


def _token_view(t: AgentToken) -> dict[str, Any]:
    return {
        "id": t.pk, "name": t.name, "created_at": t.created_at, "last_used_at": t.last_used_at,
        "last_used_ip": t.last_used_ip, "revoked_at": t.revoked_at,
    }  # fmt: skip


class ServerTokensView(APIView):
    """Agent tokenlari ro'yxati: qiymatsiz (faqat xesh saqlanadi)."""

    permission_classes = OWNER

    def get(self, request: Request, pk: str) -> HttpResponse:
        if not Server.objects.filter(pk=pk).exists():
            return error_response("not_found", "Server topilmadi.", 404)
        tokens = AgentToken.objects.filter(server_id=pk).order_by("-created_at")
        return Response({"items": [_token_view(t) for t in tokens]})


class ServerTokenDetailView(APIView):
    permission_classes = OWNER

    def delete(self, request: Request, pk: str, token_id: int) -> HttpResponse:
        token = AgentToken.objects.filter(
            pk=token_id, server_id=pk, revoked_at__isnull=True
        ).first()
        if token is None:
            return error_response("not_found", "Faol token topilmadi.", 404)
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
        record(
            "token.revoke",
            request=request._request,
            object_type="agent_token",
            object_id=token.pk,
            after={"server": str(pk)},
        )
        return HttpResponse(status=204)


class ServerAgentUpdateView(APIView):
    """Agentni yangilash (FR-AGT-008): faqat Owner. POST — so'rash, DELETE — bekor qilish.

    Core `update` buyrug'ini ingest javobiga qo'shadi; agent imzoni o'zi tekshiradi (14.5.4). Host nishon
    versiyaga yetgach so'rov o'zi tugaydi va `agent_updated` voqeasi yoziladi.
    """

    permission_classes = OWNER

    def post(self, request: Request, pk: str) -> HttpResponse:
        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        target, reason = agent_update.request_update(server)
        if target is None:
            return error_response("conflict", reason or "Yangilab bo'lmaydi.", 409)
        server.agent_update_to = target
        server.save(update_fields=["agent_update_to"])
        HostEvent.objects.create(
            server=server,
            type="agent_update_requested",
            data={"from": server.agent_version, "to": target, "by": _login(request)},
        )
        record(
            "server.agent_update",
            request=request._request,
            object_type="server",
            object_id=server.pk,
            after={"to": target},
        )
        return Response(ServerSerializer(server).data, status=202)

    def delete(self, request: Request, pk: str) -> HttpResponse:
        server = _server(pk)
        if server is None:
            return error_response("not_found", "Server topilmadi.", 404)
        if not server.agent_update_to:
            return error_response("conflict", "Yangilanish so'ralmagan.", 409)
        cancelled, server.agent_update_to = server.agent_update_to, ""
        server.save(update_fields=["agent_update_to"])
        HostEvent.objects.create(
            server=server,
            type="agent_update_cancelled",
            data={"to": cancelled, "by": _login(request)},
        )
        record(
            "server.agent_update_cancel",
            request=request._request,
            object_type="server",
            object_id=server.pk,
        )
        return Response(ServerSerializer(server).data)
