"""HTTP va TCP tekshiruvlarini bajarish (TZ 6.8, 18.4). Chiquvchi so'rovlar SSRF filtridan o'tadi:
manzil aniqlangach shaxsiy/loopback/link-local diapazonlar rad etiladi (`allow_private` bilan o'zgartiriladi),
har yo'naltirishda qayta tekshiriladi va ulanish aynan tekshirilgan IP ga qilinadi (DNS rebinding oldini olish)."""

import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

DEFAULT_MAX_BODY = 65536
MAX_REDIRECTS_CAP = 10
_RANGE = re.compile(r"^(\d{3})-(\d{3})$")


@dataclass
class Outcome:
    ok: bool
    status_code: int | None = None
    total_ms: int | None = None
    dns_ms: int | None = None
    connect_ms: int | None = None
    tls_ms: int | None = None
    ttfb_ms: int | None = None
    error_kind: str | None = (
        None  # timeout, dns, connect, tls, status, keyword, redirect_loop, blocked, config
    )
    detail: dict[str, Any] = field(default_factory=dict)


def ms(seconds: float) -> int:
    return int(seconds * 1000)


def is_blocked(ip: str) -> bool:
    """SSRF: core o'z ichki tarmog'iga murojaat qilmasligi kerak (TZ 6.8)."""
    addr = ipaddress.ip_address(ip)
    return bool(
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
    )  # fmt: skip


def resolve(host: str, port: int, *, allow_private: bool) -> tuple[str, float]:
    """Hostni bitta xavfsiz IP ga aylantiradi. Qaytadi: (ip, dns_soniya). Xato: `LookupError`/`PermissionError`."""
    started = time.monotonic()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise LookupError(str(exc)) from exc
    took = time.monotonic() - started
    addresses = [str(i[4][0]) for i in infos]
    if not addresses:
        raise LookupError("manzil topilmadi")
    if not allow_private:
        for address in addresses:
            if is_blocked(address.split("%")[0]):
                raise PermissionError(f"{host} ichki manzilga ({address}) aniqlanadi")
    return addresses[0], took


def parse_expected(spec: list[Any]) -> list[tuple[int, int]]:
    """[200, "300-399"] -> [(200,200),(300,399)]."""
    out = []
    for item in spec:
        m = _RANGE.match(str(item))
        out.append((int(m[1]), int(m[2])) if m else (int(item), int(item)))
    return out


def check_http(config: dict[str, Any], timeout_s: int) -> Outcome:
    started = time.monotonic()
    allow_private = bool(config.get("allow_private"))
    method = config.get("method", "GET")
    max_redirects = min(int(config.get("max_redirects", 5)), MAX_REDIRECTS_CAP)
    follow = bool(config.get("follow_redirects", True))
    max_body = int(config.get("max_body_bytes", DEFAULT_MAX_BODY))
    expected = parse_expected(config.get("expected_status", [200]))
    url = config["url"]
    hops = 0
    dns_total = connect_ms = tls_ms = ttfb_ms = None
    marks: dict[str, float] = {}

    def trace(event: str, info: dict[str, Any]) -> None:
        marks[event] = time.monotonic()

    while True:
        parts = urlsplit(url)
        host, scheme = parts.hostname or "", parts.scheme
        port = parts.port or (443 if scheme == "https" else 80)
        try:
            pinned = config.get("resolve_to") if hops == 0 and config.get("resolve_to") else None
            if pinned:
                ip, dns_s = pinned, 0.0
                if not allow_private and is_blocked(pinned):
                    raise PermissionError(f"resolve_to ichki manzil ({pinned})")
            else:
                ip, dns_s = resolve(host, port, allow_private=allow_private)
        except LookupError as exc:
            return Outcome(
                False,
                total_ms=ms(time.monotonic() - started),
                error_kind="dns",
                detail={"error": str(exc)[:200]},
            )
        except PermissionError as exc:
            return Outcome(
                False,
                total_ms=ms(time.monotonic() - started),
                error_kind="blocked",
                detail={"error": str(exc)[:200]},
            )
        dns_total = ms(dns_s) + (dns_total or 0)

        # Ulanish tekshirilgan IP ga; Host va SNI asl nomda (sertifikat to'g'ri tekshiriladi).
        netloc = f"[{ip}]" if ":" in ip else ip
        target = urlunsplit((scheme, f"{netloc}:{port}", parts.path or "/", parts.query, ""))
        headers = {
            **(config.get("headers") or {}),
            "Host": parts.netloc,
            "User-Agent": "nazoratchi-prober/1",
        }
        remaining = max(0.5, timeout_s - (time.monotonic() - started))
        marks.clear()
        try:
            with httpx.Client(
                timeout=remaining,
                verify=bool(config.get("verify_tls", True)),
                follow_redirects=False,
            ) as client:
                request = client.build_request(
                    method,
                    target,
                    headers=headers,
                    extensions={"sni_hostname": host, "trace": trace},
                )
                response = client.send(request, stream=True)
                try:
                    body = b""
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) >= max_body:
                            break
                finally:
                    response.close()
        except httpx.TimeoutException:
            return Outcome(
                False,
                total_ms=ms(time.monotonic() - started),
                dns_ms=dns_total,
                error_kind="timeout",
            )
        except httpx.ConnectError as exc:
            kind = (
                "tls"
                if "CERTIFICATE" in str(exc).upper() or "SSL" in str(exc).upper()
                else "connect"
            )
            return Outcome(
                False,
                total_ms=ms(time.monotonic() - started),
                dns_ms=dns_total,
                error_kind=kind,
                detail={"error": str(exc)[:200]},
            )
        except httpx.HTTPError as exc:
            return Outcome(
                False,
                total_ms=ms(time.monotonic() - started),
                dns_ms=dns_total,
                error_kind="connect",
                detail={"error": type(exc).__name__},
            )

        if "connection.connect_tcp.started" in marks and "connection.connect_tcp.complete" in marks:
            connect_ms = ms(
                marks["connection.connect_tcp.complete"] - marks["connection.connect_tcp.started"]
            )
        if "connection.start_tls.started" in marks and "connection.start_tls.complete" in marks:
            tls_ms = ms(
                marks["connection.start_tls.complete"] - marks["connection.start_tls.started"]
            )
        sent = marks.get("http11.send_request_headers.complete") or marks.get(
            "http11.send_request_body.complete"
        )
        got = marks.get("http11.receive_response_headers.complete")
        ttfb_ms = ms(got - sent) if sent and got else None

        status = response.status_code
        if follow and 300 <= status < 400 and response.headers.get("location"):
            hops += 1
            if hops > max_redirects:
                return Outcome(
                    False,
                    status,
                    ms(time.monotonic() - started),
                    dns_total,
                    connect_ms,
                    tls_ms,
                    ttfb_ms,
                    "redirect_loop",
                )
            url = urljoin(url, response.headers["location"])
            if urlsplit(url).scheme not in ("http", "https"):
                return Outcome(
                    False,
                    status,
                    ms(time.monotonic() - started),
                    dns_total,
                    connect_ms,
                    tls_ms,
                    ttfb_ms,
                    "blocked",
                    {"error": "sxema"},
                )
            continue
        break

    total = ms(time.monotonic() - started)
    base: dict[str, Any] = {
        "status_code": status,
        "total_ms": total,
        "dns_ms": dns_total,
        "connect_ms": connect_ms,
        "tls_ms": tls_ms,
        "ttfb_ms": ttfb_ms,
    }
    if not any(lo <= status <= hi for lo, hi in expected):
        return Outcome(False, error_kind="status", **{**base, "detail": {"final_url_host": host}})
    keyword = config.get("keyword")
    if keyword:
        found = keyword["text"] in body.decode("utf-8", errors="replace")
        wanted = keyword.get("mode", "contains") == "contains"
        if found != wanted:
            return Outcome(False, error_kind="keyword", **base)
    return Outcome(True, **base)


def check_tcp(config: dict[str, Any], timeout_s: int) -> Outcome:
    started = time.monotonic()
    host, port = config["host"], int(config["port"])
    expect_open = config.get("expect", "open") == "open"
    try:
        ip, dns_s = resolve(host, port, allow_private=bool(config.get("allow_private")))
    except LookupError as exc:
        return Outcome(
            False,
            total_ms=ms(time.monotonic() - started),
            error_kind="dns",
            detail={"error": str(exc)[:200]},
        )
    except PermissionError as exc:
        return Outcome(
            False,
            total_ms=ms(time.monotonic() - started),
            error_kind="blocked",
            detail={"error": str(exc)[:200]},
        )
    connect_started = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout_s):
            is_open = True
    except TimeoutError:
        return Outcome(
            False, total_ms=ms(time.monotonic() - started), dns_ms=ms(dns_s), error_kind="timeout"
        )
    except OSError:
        is_open = False
    took = ms(time.monotonic() - connect_started)
    total = ms(time.monotonic() - started)
    if is_open == expect_open:
        return Outcome(True, total_ms=total, dns_ms=ms(dns_s), connect_ms=took if is_open else None)
    return Outcome(
        False,
        total_ms=total,
        dns_ms=ms(dns_s),
        connect_ms=took if is_open else None,
        error_kind="connect" if expect_open else "status",
        detail={"expect": "open" if expect_open else "closed"},
    )


def run_check(probe_type: str, config: dict[str, Any], timeout_s: int) -> Outcome:
    if probe_type == "http":
        return check_http(config, timeout_s)
    if probe_type == "tcp":
        return check_tcp(config, timeout_s)
    return Outcome(
        False,
        error_kind="config",
        detail={"error": f"{probe_type} turi hali qo'llab-quvvatlanmaydi"},
    )
