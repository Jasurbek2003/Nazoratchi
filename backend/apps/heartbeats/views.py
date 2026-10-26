"""`GET|POST /hb/<token>[?status=ok|fail][&msg=...][&duration=...]` (TZ 9.14).

Javob: `200 ok` (matn). Noma'lum token `404` (mavjudligini oshkor qilmaydi); token bo'yicha daqiqada 10 ta.
`status=fail` darhol alert beradi (AL-048, B7); kelmasa AL-047.
"""

import re

from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core import ratelimit
from apps.registry.models import hash_token

from .models import HeartbeatJob

_TOKEN_RE = re.compile(r"^hb_[A-Za-z0-9_-]{8,64}$")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def beat(request: HttpRequest, token: str) -> HttpResponse:
    job = None
    if _TOKEN_RE.match(token):
        job = HeartbeatJob.objects.filter(token_hash=hash_token(token), enabled=True).first()
    if job is None:
        return HttpResponse("topilmadi\n", status=404, content_type="text/plain; charset=utf-8")

    decision = ratelimit.hit("hb", str(job.id), limit=10, window_s=60)
    if not decision.allowed:
        return HttpResponse(
            "juda ko'p\n",
            status=429,
            content_type="text/plain; charset=utf-8",
            headers={"Retry-After": str(decision.retry_after)},
        )

    status = request.GET.get("status", "ok")
    if status not in ("ok", "fail"):
        return HttpResponse(
            "status ok yoki fail bo'lishi kerak\n",
            status=400,
            content_type="text/plain; charset=utf-8",
        )
    duration = request.GET.get("duration", "")
    job.last_beat_at = timezone.now()
    job.last_ok = status == "ok"
    job.last_message = request.GET.get("msg", "")[:200]
    job.last_duration_s = int(duration) if duration.isdigit() and len(duration) <= 9 else None
    job.save(update_fields=["last_beat_at", "last_ok", "last_message", "last_duration_s"])
    return HttpResponse("ok\n", content_type="text/plain; charset=utf-8")
