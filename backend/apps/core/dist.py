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

_DIST_NAME = re.compile(
    r"^(nazoratchi-agent-(amd64|arm64)|VERSION|SHA256SUMS|SHA256SUMS\.minisig)$"
)
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


# ---- Agent yangilanishi (FR-AGT-008, TZ 7.7.3) ----
# Core faqat *maslahat* beradi: haqiqiy versiya va xesh agent tomonida imzolangan SHA256SUMS dan tekshiriladi
# (minisign maxfiy kaliti core'da yo'q, 14.5.4). Core noto'g'ri versiya bildirsa, agent rad etadi.

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
AGENT_ARCHES = ("amd64", "arm64")


def parse_version(value: str) -> tuple[int, int, int] | None:
    """`1.2.3` yoki `nazoratchi-agent/1.2.3` (X-Nazoratchi-Agent sarlavhasi) ni sonlar uchligiga."""
    text = value.rsplit("/", 1)[-1].strip().removeprefix("v")
    if not VERSION_RE.match(text):
        return None
    major, minor, patch = (int(p) for p in text.split("."))
    return major, minor, patch


def latest_agent_version() -> str | None:
    """Tarqatish papkasidagi `VERSION` (release.yml yozadi; SHA256SUMS ichida imzolangan). Yo'q/yaroqsiz bo'lsa None."""
    path = Path(settings.AGENT_DIST_DIR) / "VERSION"
    try:
        if path.is_symlink() or path.stat().st_size > 64:
            return None
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if VERSION_RE.match(text) else None


def agent_binary_sha256(arch: str) -> str | None:
    """`SHA256SUMS` dan binar xeshi (maslahat; agent imzolangan nusxadan qayta tekshiradi)."""
    if arch not in AGENT_ARCHES:
        return None
    try:
        lines = (
            (Path(settings.AGENT_DIST_DIR) / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        )
    except OSError:
        return None
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip("*") == f"nazoratchi-agent-{arch}":
            digest = fields[0].lower()
            return digest if re.fullmatch(r"[0-9a-f]{64}", digest) else None
    return None


def update_command(arch: str) -> dict[str, str] | None:
    """Ingest javobidagi `update` buyrug'i (TZ 7.5.3). Reliz fayllari to'liq bo'lmasa None."""
    version = latest_agent_version()
    digest = agent_binary_sha256(arch)
    if version is None or digest is None:
        return None
    return {
        "type": "update",
        "version": version,
        "sha256": digest,
        "url": f"/agent/v1/nazoratchi-agent-{arch}",
    }
