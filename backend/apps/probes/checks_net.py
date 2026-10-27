"""TLS va DNS tekshiruvlari (TZ 18.4.3-4, FR-TLS-001..004, FR-DNS-001..003).

`checks.py` dagi SSRF yordamchilaridan foydalanadi (`resolve`, `is_blocked`). `checks.run_check` shu yerga yo'naltiradi.
"""

import socket
import ssl
import time
from datetime import UTC, datetime
from typing import Any

from .checks import Outcome, is_blocked, ms, resolve

PUBLIC_RESOLVERS = ("8.8.8.8", "1.1.1.1", "9.9.9.9")


# ----------------------------------------------------------------------- TLS
def san_matches(hostname: str, sans: list[str]) -> bool:
    """Hostname SAN ro'yxatiga mos keladimi (bitta darajali wildcard `*.example.uz` bilan)."""
    host = hostname.lower().rstrip(".")
    for san in sans:
        pattern = san.lower().rstrip(".")
        if pattern == host:
            return True
        if pattern.startswith("*.") and "." in host and host.split(".", 1)[1] == pattern[2:]:
            return True
    return False


def read_certificate(ip: str, port: int, sni: str, timeout_s: int) -> bytes:
    """Sertifikatni TEKSHIRUVSIZ o'qiydi (nom mos kelmasa yoki muddati o'tgan bo'lsa ham ko'rish uchun). DER."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with (
        socket.create_connection((ip, port), timeout=timeout_s) as raw,
        context.wrap_socket(raw, server_hostname=sni) as tls,
    ):
        der = tls.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError("sertifikat berilmadi")
    return der


def chain_trusted(ip: str, port: int, sni: str, timeout_s: int) -> bool:
    """Zanjir ishonchli CA gacha to'liqmi (hostname alohida tekshiriladi)."""
    context = ssl.create_default_context()
    context.check_hostname = False
    try:
        with (
            socket.create_connection((ip, port), timeout=timeout_s) as raw,
            context.wrap_socket(raw, server_hostname=sni),
        ):
            return True
    except ssl.SSLCertVerificationError:
        return False


def check_tls(config: dict[str, Any], timeout_s: int) -> Outcome:
    from cryptography import x509

    started = time.monotonic()
    host, port = config["host"], int(config.get("port", 443))
    sni = config.get("sni") or host
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
    try:
        connect_started = time.monotonic()
        der = read_certificate(ip, port, sni, timeout_s)
        connect_ms = ms(time.monotonic() - connect_started)
        cert = x509.load_der_x509_certificate(der)
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            sans = list(san_ext.value.get_values_for_type(x509.DNSName))
        except x509.ExtensionNotFound:
            sans = []
        chain_ok = (
            chain_trusted(ip, port, sni, timeout_s) if config.get("check_chain", True) else None
        )
    except TimeoutError:
        return Outcome(
            False, total_ms=ms(time.monotonic() - started), dns_ms=ms(dns_s), error_kind="timeout"
        )
    except ssl.SSLError as exc:
        return Outcome(
            False,
            total_ms=ms(time.monotonic() - started),
            dns_ms=ms(dns_s),
            error_kind="tls",
            detail={"error": str(exc)[:200]},
        )
    except (OSError, ValueError) as exc:
        return Outcome(
            False,
            total_ms=ms(time.monotonic() - started),
            dns_ms=ms(dns_s),
            error_kind="connect",
            detail={"error": type(exc).__name__},
        )
    not_after = cert.not_valid_after_utc
    days_left = int((not_after - datetime.now(UTC)).total_seconds() // 86400)
    hostname_ok = san_matches(sni, sans) if config.get("check_hostname", True) else None
    detail = {
        "not_after": not_after.isoformat(), "days_left": days_left, "issuer": cert.issuer.rfc4514_string()[:300],
        "subject": cert.subject.rfc4514_string()[:300], "san": sans[:50], "chain_ok": chain_ok, "hostname_ok": hostname_ok,
    }  # fmt: skip
    return Outcome(
        True,
        total_ms=ms(time.monotonic() - started),
        dns_ms=ms(dns_s),
        connect_ms=connect_ms,
        detail=detail,
    )


# ----------------------------------------------------------------------- DNS
def dns_query(
    resolver_ip: str, name: str, rtype: str, timeout_s: float
) -> tuple[list[str], str, int]:
    """(javoblar, rcode, kechikish ms). rcode: NOERROR, NODATA, NXDOMAIN, TIMEOUT, SERVFAIL, ERROR."""
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.lifetime = timeout_s
    started = time.monotonic()
    try:
        answer = resolver.resolve(name, rtype, raise_on_no_answer=False)
        values = sorted({r.to_text() for r in answer}) if answer.rrset else []
        return values, "NOERROR" if values else "NODATA", ms(time.monotonic() - started)
    except dns.resolver.NXDOMAIN:
        return [], "NXDOMAIN", ms(time.monotonic() - started)
    except dns.resolver.LifetimeTimeout:
        return [], "TIMEOUT", ms(time.monotonic() - started)
    except dns.resolver.NoNameservers:
        return [], "SERVFAIL", ms(time.monotonic() - started)
    except dns.exception.DNSException:
        return [], "ERROR", ms(time.monotonic() - started)


def authoritative_ns(name: str, timeout_s: float) -> str | None:
    """Domenning o'z NS serveri IP si (`ns:auto`); ichki manzil bo'lsa rad etiladi (SSRF)."""
    for ns_host in dns_query(PUBLIC_RESOLVERS[0], name, "NS", timeout_s)[0]:
        for ip in dns_query(PUBLIC_RESOLVERS[0], ns_host.rstrip("."), "A", timeout_s)[0]:
            if not is_blocked(ip):
                return ip
    return None


def check_dns(config: dict[str, Any], timeout_s: int) -> Outcome:
    started = time.monotonic()
    name, rtype = config["name"], config.get("rtype", "A")
    expected = {str(x) for x in config.get("expected", [])}
    retired = {str(x) for x in config.get("retired_ips", [])}
    results: list[dict[str, Any]] = []
    for spec in config.get("resolvers", list(PUBLIC_RESOLVERS)):
        ip = authoritative_ns(name, timeout_s) if spec == "ns:auto" else spec
        if ip is None or (is_blocked(ip) and not config.get("allow_private")):
            results.append(
                {
                    "resolver": spec,
                    "answers": [],
                    "matches": False,
                    "rcode": "BLOCKED" if ip else "NO_NS",
                    "latency_ms": None,
                }
            )
            continue
        answers, rcode, latency = dns_query(ip, name, rtype, timeout_s)
        matches = (set(answers) == expected) if expected else bool(answers)
        results.append(
            {
                "resolver": spec,
                "answers": answers,
                "matches": matches,
                "rcode": rcode,
                "latency_ms": latency,
            }
        )
    responded = [r for r in results if r["rcode"] not in ("TIMEOUT", "ERROR", "BLOCKED", "NO_NS")]
    found_retired = sorted({a for r in results for a in r["answers"]} & retired)
    detail: dict[str, Any] = {"resolvers": results, "retired": found_retired}
    total = ms(time.monotonic() - started)
    if not responded:
        return Outcome(
            False, total_ms=total, error_kind="dns", detail=detail
        )  # hech bir resolver javob bermadi
    if all(r["matches"] for r in responded):
        return Outcome(True, total_ms=total, detail=detail)
    kind = "nxdomain" if all(r["rcode"] == "NXDOMAIN" for r in responded) else "mismatch"
    return Outcome(False, total_ms=total, error_kind=kind, detail=detail)
