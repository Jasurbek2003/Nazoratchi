"""`POST /ingest/v1/metrics` (TZ 7.5.2, 9.13)."""

import json
import logging
import zlib
from datetime import timedelta

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.http import error_response
from apps.registry.models import AgentToken, Server, hash_token

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
    server.status = Server.Status.ONLINE
    server.agent_version = request.headers.get("X-Nazoratchi-Agent", "")[:40]
    if facts:
        server.facts = {**server.facts, **facts}
    server.save(update_fields=["last_seen_at", "status", "agent_version", "facts"])
    # Token oxirgi ishlatilishi: har so'rovda yozmaslik uchun 1 daqiqada bir marta.
    if agent_token.last_used_at is None or now - agent_token.last_used_at > timedelta(minutes=1):
        agent_token.last_used_at = now
        agent_token.save(update_fields=["last_used_at"])

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
