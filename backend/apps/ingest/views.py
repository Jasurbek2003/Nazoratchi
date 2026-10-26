"""`POST /ingest/v1/metrics` (TZ 7.5.2, 9.13)."""

import json
import logging
import zlib
from datetime import timedelta

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.audit.services import record
from apps.core import ratelimit
from apps.core.http import error_response
from apps.core.net import client_ip
from apps.registry.models import AgentToken, EnrollToken, HostEvent, Server, hash_token

from .catalog import MAX_BODY_BYTES
from .services import ingest_batch
from .validation import BatchError, parse_batch

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15


def _authenticate(request: HttpRequest) -> tuple[Server, AgentToken] | JsonResponse:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return error_response("unauthenticated", "Authorization: Bearer <token> kerak.", 401)
    agent_token = (
        AgentToken.objects.select_related("server").filter(token_hash=hash_token(token)).first()
    )
    if agent_token is None:
        return error_response("invalid_token", "Token noto'g'ri.", 401)
    if agent_token.revoked_at is not None:
        return error_response("token_revoked", "Token bekor qilingan.", 401)
    return agent_token.server, agent_token


def _read_body(request: HttpRequest) -> bytes | JsonResponse:
    declared = int(request.META.get("CONTENT_LENGTH") or 0)
    if declared > MAX_BODY_BYTES:
        return error_response("payload_too_large", "Paket 1 MB dan katta.", 413)
    raw = request.body
    if len(raw) > MAX_BODY_BYTES:
        return error_response("payload_too_large", "Paket 1 MB dan katta.", 413)
    if request.headers.get("Content-Encoding", "").lower() == "gzip":
        # Zip-bomba himoyasi: ochilgan hajm ham 1 MB dan oshmasligi kerak.
        decoder = zlib.decompressobj(wbits=31)
        try:
            data = decoder.decompress(raw, MAX_BODY_BYTES + 1)
            if decoder.unconsumed_tail or len(data) > MAX_BODY_BYTES:
                return error_response("payload_too_large", "Ochilgan paket 1 MB dan katta.", 413)
            data += decoder.flush()
        except zlib.error:
            return error_response("bad_request", "gzip buzuq.", 400)
        return data
    return raw


@csrf_exempt
@require_POST
def ingest_metrics(request: HttpRequest) -> JsonResponse:
    auth = _authenticate(request)
    if isinstance(auth, JsonResponse):
        return auth
    server, agent_token = auth

    # NFR-SEC-007: token bo'yicha daqiqada 30 ta (normal ~4). Kesh nosoz bo'lsa o'tkaziladi (fail-open).
    decision = ratelimit.hit("ingest", str(agent_token.pk), limit=30, window_s=60)
    if not decision.allowed:
        return error_response(
            "rate_limited",
            "So'rovlar juda ko'p.",
            429,
            headers={"Retry-After": str(decision.retry_after)},
        )

    body = _read_body(request)
    if isinstance(body, JsonResponse):
        return body
    try:
        payload = json.loads(body)
    except ValueError:
        return error_response("bad_request", "JSON noto'g'ri.", 400)
    try:
        _batch_id, _seq, sent_at, raw_samples, facts = parse_batch(payload)
    except BatchError as exc:
        return error_response(
            "validation_error",
            "Paket noto'g'ri.",
            400,
            details=[{"field": exc.field, "code": "invalid", "message": exc.message}],
        )

    result = ingest_batch(server, raw_samples, sent_at)

    now = timezone.now()
    server.last_seen_at = now
    if server.status in (Server.Status.NEW, Server.Status.OFFLINE):
        server.status = (
            Server.Status.ONLINE
        )  # pauza/arxiv holati ma'lumot kelishi bilan o'zgarmaydi
    server.agent_version = request.headers.get("X-Nazoratchi-Agent", "")[:40]
    if facts:
        server.facts = {**server.facts, **facts}
    server.save(update_fields=["last_seen_at", "status", "agent_version", "facts"])
    # Token oxirgi ishlatilishi: har so'rovda yozmaslik uchun 1 daqiqada bir marta.
    if agent_token.last_used_at is None or now - agent_token.last_used_at > timedelta(minutes=1):
        agent_token.last_used_at = now
        agent_token.last_used_ip = client_ip(request)
        agent_token.save(update_fields=["last_used_at", "last_used_ip"])

    if result.rejected:
        logger.warning("ingest: %s namuna rad etildi (server=%s)", result.rejected, server.name)
    return JsonResponse(
        {
            "ok": True,
            "accepted": result.accepted,
            "rejected": result.rejected,
            "duplicate": result.duplicate,
            "clock_skew": result.clock_skew,
            "server_time": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "interval_seconds": INTERVAL_SECONDS,
            "commands": [],
        }
    )


@csrf_exempt
@require_POST
def enroll(request: HttpRequest) -> JsonResponse:
    """Bir martalik enroll token -> doimiy agent tokeni (TZ 7.5.1, FR-AGT-002)."""
    ip = client_ip(request) or "noma'lum"
    decision = ratelimit.hit(
        "enroll", ip, limit=10, window_s=3600
    )  # TZ 14.7.3: IP bo'yicha 10/soat
    if not decision.allowed:
        return error_response(
            "rate_limited",
            "So'rovlar juda ko'p.",
            429,
            headers={"Retry-After": str(decision.retry_after)},
        )
    body = _read_body(request)
    if isinstance(body, JsonResponse):
        return body
    try:
        payload = json.loads(body)
    except ValueError:
        return error_response("bad_request", "JSON noto'g'ri.", 400)
    token = payload.get("enroll_token") if isinstance(payload, dict) else None
    facts = payload.get("facts", {}) if isinstance(payload, dict) else {}
    if not isinstance(token, str) or not isinstance(facts, dict):
        return error_response(
            "validation_error", "enroll_token (matn) majburiy, facts obyekt bo'lishi kerak.", 400
        )
    hostname = str(payload.get("hostname", ""))[:80]
    version = str(payload.get("agent_version", ""))[:40]

    with transaction.atomic():
        row = (
            EnrollToken.objects.select_for_update()
            .select_related("server")
            .filter(token_hash=hash_token(token))
            .first()
        )
        now = timezone.now()
        if row is None:
            return error_response("invalid_enroll_token", "Enroll token noto'g'ri.", 401)
        if row.used_at is not None:
            return error_response("host_already_enrolled", "Bu enroll token ishlatilgan.", 409)
        if row.expires_at < now:
            return error_response(
                "enroll_token_expired", "Enroll token muddati tugagan (1 soat).", 410
            )
        row.used_at = now
        row.save(update_fields=["used_at"])
        server = row.server
        _, agent_token = AgentToken.issue(server, "agent")
        server.agent_version = version
        server.facts = {**server.facts, **facts, **({"hostname": hostname} if hostname else {})}
        server.save(update_fields=["agent_version", "facts"])
        HostEvent.objects.create(
            server=server, type="enrolled", data={"hostname": hostname, "ip": ip}
        )
    record(
        "agent.enroll",
        ip=ip,
        object_type="server",
        object_id=server.id,
        after={"hostname": hostname},
    )
    return JsonResponse(
        {
            "host_id": str(server.id),
            "agent_token": agent_token,
            "interval_seconds": INTERVAL_SECONDS,
            "server_time": timezone.now().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
    )


@csrf_exempt
@require_POST
def goodbye(request: HttpRequest) -> JsonResponse:
    """`nazoratchi-agent uninstall`: host arxivga tushadi, tokenlar bekor qilinadi (FR-AGT-013)."""
    auth = _authenticate(request)
    if isinstance(auth, JsonResponse):
        return auth
    server, _ = auth
    now = timezone.now()
    with transaction.atomic():
        server.status = Server.Status.ARCHIVED
        server.save(update_fields=["status"])
        AgentToken.objects.filter(server=server, revoked_at__isnull=True).update(revoked_at=now)
        HostEvent.objects.create(server=server, type="goodbye")
    record("agent.goodbye", ip=client_ip(request), object_type="server", object_id=server.id)
    return JsonResponse({"ok": True})
