"""Kanallar va xabarlar tarixi (TZ 9.9): kanallar faqat Owner uchun, tarix Owner va Operator uchun."""

from typing import Any

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.http import error_response
from apps.core.permissions import roles

from . import services
from .models import Channel, Notification
from .serializers import ChannelSerializer, NotificationSerializer

OWNER: list[type[BasePermission]] = [IsAuthenticated, roles("owner")]
PAGE_SIZE = 50


def _audit_view(channel: Channel) -> dict[str, Any]:
    """Auditga sirlarsiz (config yo'q): faqat tavsif maydonlari."""
    data = dict(ChannelSerializer(channel).data)
    data.pop("config_masked", None)
    return data


class ChannelListView(APIView):
    permission_classes = OWNER

    def get(self, request: Request) -> Response:
        channels = Channel.objects.order_by("name")
        return Response({"items": ChannelSerializer(channels, many=True).data})

    def post(self, request: Request) -> HttpResponse:
        serializer = ChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        config = data.pop("config")
        channel = Channel(**data)
        channel.set_config(config)
        try:
            with transaction.atomic():
                channel.save()
        except IntegrityError:
            return error_response("duplicate", "Bunday nomli kanal mavjud.", 409)
        record(
            "channel.create",
            request=request._request,
            object_type="channel",
            object_id=channel.id,
            after=_audit_view(channel),
        )
        return Response(ChannelSerializer(channel).data, status=201)


class ChannelDetailView(APIView):
    permission_classes = OWNER

    def _get(self, pk: str) -> Channel | None:
        return Channel.objects.filter(pk=pk).first()

    def patch(self, request: Request, pk: str) -> HttpResponse:
        channel = self._get(pk)
        if channel is None:
            return error_response("not_found", "Kanal topilmadi.", 404)
        before = _audit_view(channel)
        serializer = ChannelSerializer(channel, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        new_config = data.pop("config", None)
        for key, value in data.items():
            setattr(channel, key, value)
        if new_config is not None:
            # Qisman yangilash: berilmagan kalit (masalan, bot_token) eskicha qoladi.
            channel.set_config({**channel.get_config(), **new_config})
        try:
            with transaction.atomic():
                channel.save()
        except IntegrityError:
            return error_response("duplicate", "Bunday nomli kanal mavjud.", 409)
        record(
            "channel.update",
            request=request._request,
            object_type="channel",
            object_id=channel.id,
            before=before,
            after=_audit_view(channel),
        )
        return Response(ChannelSerializer(channel).data)

    def delete(self, request: Request, pk: str) -> HttpResponse:
        channel = self._get(pk)
        if channel is None:
            return error_response("not_found", "Kanal topilmadi.", 404)
        before = _audit_view(channel)
        channel.delete()
        record(
            "channel.delete",
            request=request._request,
            object_type="channel",
            object_id=pk,
            before=before,
        )
        return HttpResponse(status=204)


class ChannelTestView(APIView):
    permission_classes = OWNER

    def post(self, request: Request, pk: str) -> HttpResponse:
        channel = Channel.objects.filter(pk=pk).first()
        if channel is None:
            return error_response("not_found", "Kanal topilmadi.", 404)
        notification = services.send_test(channel)
        record(
            "channel.test",
            request=request._request,
            object_type="channel",
            object_id=channel.id,
            after={"status": notification.status},
        )
        ok = notification.status == Notification.Status.SENT
        return Response(
            {"ok": ok, "status": notification.status, "error": notification.error},
            status=200 if ok else 502,
        )


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated, roles("owner", "operator")]

    def get(self, request: Request) -> HttpResponse:
        rows = Notification.objects.select_related("channel").order_by("-id")
        if channel := request.query_params.get("channel"):
            rows = rows.filter(channel_id=channel)
        if status := request.query_params.get("status"):
            rows = rows.filter(status=status)
        before = request.query_params.get("before")
        if before:
            if not before.isdigit():
                return error_response("validation_error", "before butun son bo'lishi kerak.", 400)
            rows = rows.filter(id__lt=int(before))
        page = list(rows[: PAGE_SIZE + 1])
        has_more = len(page) > PAGE_SIZE
        page = page[:PAGE_SIZE]
        return Response(
            {
                "items": NotificationSerializer(page, many=True).data,
                "next_before": page[-1].id if has_more else None,
            }
        )
