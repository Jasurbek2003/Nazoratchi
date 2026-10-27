"""Agent tarqatish (TZ 7.7.1, 15.x): `GET /install.sh` va `GET /agent/v1/<fayl>`.

`install.sh` repodagi shablon (`deploy/agent/install.sh`): core uni berishda `__CORE_URL__` va `__MINISIGN_PUBKEY__`
ni almashtiradi (qiymatlar qat'iy tekshiriladi: skriptga buyruq kiritib bo'lmasligi uchun). Binar va imzolar
`AGENT_DIST_DIR` dan (release artefaktlari); nomi oq ro'yxat bo'yicha.
"""

import re
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

_DIST_NAME = re.compile(r"^(nazoratchi-agent-(amd64|arm64)|SHA256SUMS|SHA256SUMS\.minisig)$")
_SAFE_URL = re.compile(r"^https?://[A-Za-z0-9._:\[\]-]+(/[A-Za-z0-9._~/-]*)?$")
_SAFE_KEY = re.compile(r"^[A-Za-z0-9+/=]{40,120}$")  # minisign ochiq kaliti (base64)


def _text(message: str, status: int) -> HttpResponse:
    return HttpResponse(message + "\n", status=status, content_type="text/plain; charset=utf-8")


@require_GET
def install_script(request: HttpRequest) -> HttpResponse:
    path = Path(settings.AGENT_INSTALL_SCRIPT)
    if not path.is_file():
        raise Http404("install.sh topilmadi")
    key = settings.MINISIGN_PUBKEY
    if not _SAFE_KEY.match(key):
        # Imzo kaliti yo'q: tekshiruvsiz skript tarqatilmaydi (ta'minot zanjiri himoyasi)
        return _text("echo 'xato: core da MINISIGN_PUBKEY sozlanmagan' >&2; exit 1", 503)
    if not _SAFE_URL.match(settings.PUBLIC_URL):
        return _text("echo 'xato: core da PUBLIC_URL yaroqsiz' >&2; exit 1", 503)
    body = (
        path.read_text(encoding="utf-8")
        .replace("__CORE_URL__", settings.PUBLIC_URL)
        .replace("__MINISIGN_PUBKEY__", key)
    )
    response = HttpResponse(body, content_type="text/x-shellscript; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def agent_file(request: HttpRequest, name: str) -> FileResponse:
    if not _DIST_NAME.match(name):
        raise Http404
    path = Path(settings.AGENT_DIST_DIR) / name
    if not path.is_file() or path.is_symlink():
        raise Http404
    response = FileResponse(path.open("rb"), content_type="application/octet-stream")
    response["Cache-Control"] = "no-cache"
    return response
