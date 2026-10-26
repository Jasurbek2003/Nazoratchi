"""Sessiyaning mutlaq muddati (TZ 14.3.4): harakatsizlik 12 soat (Django sozlamasi), mutlaq 7 kun."""

from collections.abc import Callable

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

ABSOLUTE_LIFETIME_S = 7 * 24 * 3600


class AbsoluteSessionTimeoutMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        login_at = request.session.get("login_at")
        if login_at is not None and timezone.now().timestamp() - login_at > ABSOLUTE_LIFETIME_S:
            request.session.flush()
            request.user = AnonymousUser()
        return self.get_response(request)
