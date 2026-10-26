"""Autentifikatsiya endpointlari (TZ 9.2): kirish, chiqish, profil, sessiyalar."""

import uuid
from typing import Any

from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.http import error_response
from apps.core.net import client_ip

from .models import User, UserSession
from .serializers import LoginSerializer, MeUpdateSerializer
from .services import AccountLocked, InvalidCredentials, verify_login


def user_payload(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "login": user.login,
        "role": user.role,
        "language": user.language,
        "timezone": user.timezone,
        "mfa_enabled": bool(user.totp_secret_enc),
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """SPA birinchi so'rovdan oldin CSRF cookie oladi."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        return Response(status=204)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request: Request) -> HttpResponse:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = verify_login(request._request, data["login"], data["password"])
        except InvalidCredentials:
            return error_response("unauthenticated", "Login yoki parol noto'g'ri.", 401)
        except AccountLocked as exc:
            return error_response(
                "account_locked",
                "Hisob vaqtincha bloklangan. Keyinroq urinib ko'ring.",
                423,
                headers={"Retry-After": str(exc.retry_after)},
            )
        django_request = request._request
        login(django_request, user)
        now = timezone.now()
        django_request.session["login_at"] = int(now.timestamp())
        # Ro'yxat uchun metadata sessiya ma'lumotida (sessions.SessionStore shu yerdan ustunlarga ko'chiradi).
        django_request.session["_pid"] = str(uuid.uuid4())
        django_request.session["_ip"] = client_ip(django_request)
        django_request.session["_ua"] = request.headers.get("User-Agent", "")[:300]
        django_request.session["_created"] = now.isoformat()
        record("login", user=user, request=django_request, object_type="user", object_id=user.id)
        return Response({"user": user_payload(user)})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        record("logout", request=request._request, object_type="user", object_id=request.user.pk)
        logout(request._request)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(user_payload(_user(request)))

    def patch(self, request: Request) -> HttpResponse:
        serializer = MeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = _user(request)
        changed: list[str] = []
        for field in ("language", "timezone"):
            if field in data:
                setattr(user, field, data[field])
                changed.append(field)
        if "new_password" in data:
            if not user.check_password(data["current_password"]):
                return error_response(
                    "validation_error",
                    "Joriy parol noto'g'ri.",
                    400,
                    details=[
                        {
                            "field": "current_password",
                            "code": "invalid",
                            "message": "Parol noto'g'ri.",
                        }
                    ],
                )
            try:
                validate_password(data["new_password"], user)
            except DjangoValidationError as exc:
                return error_response(
                    "validation_error",
                    "Yangi parol talablarga javob bermaydi.",
                    400,
                    details=[
                        {"field": "new_password", "code": "weak", "message": m}
                        for m in exc.messages
                    ],
                )
            user.set_password(data["new_password"])
            changed.append("password")
        if changed:
            user.save()
            if "password" in changed:
                update_session_auth_hash(
                    request._request, user
                )  # boshqa sessiyalar yaroqsiz bo'ladi
                record(
                    "password_changed",
                    request=request._request,
                    object_type="user",
                    object_id=user.id,
                )
            record(
                "profile.update",
                request=request._request,
                object_type="user",
                object_id=user.id,
                after={k: v for k, v in data.items() if "password" not in k},
            )
        return Response(user_payload(user))


class SessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        current = request.session.session_key
        rows = UserSession.objects.filter(user_id=request.user.pk).order_by("-created_at")
        return Response(
            {
                "items": [
                    {
                        "id": str(s.public_id),
                        "current": s.session_key == current,
                        "ip": s.ip,
                        "user_agent": s.user_agent,
                        "created_at": s.created_at.isoformat(),
                        "expires_at": s.expire_date.isoformat(),
                    }
                    for s in rows
                ]
            }
        )


class SessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, public_id: uuid.UUID) -> HttpResponse:
        target = UserSession.objects.filter(user_id=request.user.pk, public_id=public_id).first()
        if target is None:
            return error_response("not_found", "Sessiya topilmadi.", 404)
        record(
            "session.revoke", request=request._request, object_type="session", object_id=public_id
        )
        if target.session_key == request.session.session_key:
            logout(
                request._request
            )  # joriy sessiya: qatorni o'chirish o'rniga to'g'ri chiqish (aks holda 400)
        else:
            target.delete()
        return Response(status=204)


class LogoutAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        record(
            "logout_all", request=request._request, object_type="user", object_id=request.user.pk
        )
        UserSession.objects.filter(user_id=request.user.pk).exclude(
            session_key=request.session.session_key
        ).delete()
        logout(
            request._request
        )  # joriy sessiya oxirida: qatorni qo'lda o'chirsak Django qayta saqlay olmaydi
        return Response(status=204)


def _user(request: Request) -> User:
    user = request.user
    if not isinstance(user, User):  # IsAuthenticated dan keyin bo'lmasligi kerak
        raise PermissionDenied
    return user
