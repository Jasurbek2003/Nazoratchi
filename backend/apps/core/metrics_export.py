"""`/metrics` — core'ning o'z ko'rsatkichlari (FR-SYS-001), Prometheus matn formati. Faqat ichki: `METRICS_TOKEN` bo'lsa
`Authorization: Bearer`, bo'lmasa faqat loopback manzildan (TZ 6: /metrics, /healthz faqat ichki yoki token bilan)."""

import hmac
from collections.abc import Iterable
from datetime import datetime

from django.conf import settings
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.core.net import client_ip

Line = tuple[str, dict[str, str], float]


def _fmt(name: str, labels: dict[str, str], value: float) -> str:
    lab = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{lab}}} {value:g}" if lab else f"{name} {value:g}"


def collect(now: datetime) -> Iterable[Line]:
    from apps.alerts.models import AlertInstance, EvaluatorState, Incident
    from apps.metrics.models import Series
    from apps.notifications.models import Notification
    from apps.probes.models import Probe
    from apps.registry.models import Server

    yield "nazoratchi_up", {}, 1
    for srv in Server.objects.values("status").annotate(n=Count("id")):
        yield "nazoratchi_servers", {"status": srv["status"]}, srv["n"]
    for inc in (
        Incident.objects.exclude(status="resolved").values("severity").annotate(n=Count("id"))
    ):
        yield "nazoratchi_incidents_open", {"severity": inc["severity"]}, inc["n"]
    for alert in AlertInstance.objects.exclude(state="ok").values("state").annotate(n=Count("id")):
        yield "nazoratchi_alert_instances", {"state": alert["state"]}, alert["n"]
    queued = Notification.objects.filter(status="queued")
    yield "nazoratchi_notifications_queued", {}, queued.count()
    oldest = queued.order_by("next_attempt_at").values_list("next_attempt_at", flat=True).first()
    yield (
        "nazoratchi_notifications_oldest_queued_age_seconds",
        {},
        max(0.0, (now - oldest).total_seconds()) if oldest else 0,
    )
    state = EvaluatorState.objects.filter(pk=1).first()
    if state is not None:
        yield (
            "nazoratchi_evaluator_last_run_age_seconds",
            {},
            (now - state.last_run_at).total_seconds(),
        )
        yield "nazoratchi_evaluator_duration_ms", {}, state.last_duration_ms
    for probe in Probe.objects.filter(enabled=True).values("state").annotate(n=Count("id")):
        yield "nazoratchi_probes", {"state": probe["state"]}, probe["n"]
    yield "nazoratchi_metric_series", {}, Series.objects.count()


def _allowed(request: HttpRequest) -> bool:
    token = settings.METRICS_TOKEN
    if token:
        header = request.headers.get("Authorization", "")
        return hmac.compare_digest(header.encode(), f"Bearer {token}".encode())
    return client_ip(request) in ("127.0.0.1", "::1")


@require_GET
def metrics(request: HttpRequest) -> HttpResponse:
    if not _allowed(request):
        return HttpResponse("ruxsat yo'q\n", status=403, content_type="text/plain; charset=utf-8")
    body = "\n".join(_fmt(*line) for line in collect(timezone.now())) + "\n"
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")
