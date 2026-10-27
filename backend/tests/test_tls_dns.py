"""TLS va DNS tekshiruvlari, sertifikat/DNS/konteyner qoidalari (B6 S5; FR-TLS-001..004, FR-DNS-001..003, 008)."""

import datetime as dt
import socket
import ssl
import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.test import Client
from django.utils import timezone

from apps.alerts import conditions
from apps.alerts.catalog import sync_built_in
from apps.alerts.conditions import ConditionError, validate_condition
from apps.alerts.engine import run_cycle
from apps.alerts.models import AlertInstance, AlertRule, Incident
from apps.notifications.models import Notification
from apps.probes import checks, checks_net, services
from apps.probes.models import CertStatus, DnsChange, Probe
from apps.registry.models import Domain, Project, Server, Setting

from .test_accounts import csrf_client, csrf_headers, login, make_user
from .test_alerts import T0, alive, channel, new_server, only, put

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- haqiqiy TLS server (o'zi imzolagan sertifikat)
def make_cert(tmp: Path, days: int, names: list[str]) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days, hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
        .sign(key, hashes.SHA256())
    )  # fmt: skip
    cert_path, key_path = tmp / f"c{days}.pem", tmp / f"k{days}.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def serve_tls(cert: str, key: str) -> tuple[int, Any]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    stop = threading.Event()

    def loop() -> None:
        sock.settimeout(0.2)
        while not stop.is_set():
            try:
                raw, _ = sock.accept()
            except OSError:
                continue
            try:
                with context.wrap_socket(raw, server_side=True):
                    pass
            except (ssl.SSLError, OSError):
                pass

    threading.Thread(target=loop, daemon=True).start()

    def shutdown() -> None:
        stop.set()
        sock.close()

    return sock.getsockname()[1], shutdown


@pytest.fixture
def tls_server(tmp_path: Path) -> Iterator[int]:
    cert, key = make_cert(tmp_path, 10, ["nazar.example.uz", "*.example.uz"])
    port, shutdown = serve_tls(cert, key)
    yield port
    shutdown()


def tls_cfg(port: int, **extra: Any) -> dict[str, Any]:
    return {"host": "127.0.0.1", "port": port, "allow_private": True, **extra}


def test_tls_reads_certificate_details(tls_server: int) -> None:
    out = checks_net.check_tls(tls_cfg(tls_server, sni="nazar.example.uz"), 5)
    assert out.ok and out.error_kind is None
    d = out.detail
    assert 9 <= d["days_left"] <= 10
    assert d["san"] == ["nazar.example.uz", "*.example.uz"] and "nazar.example.uz" in d["subject"]
    assert d["hostname_ok"] is True
    assert d["chain_ok"] is False  # o'zi imzolagan: ishonchli CA yo'q
    assert out.connect_ms is not None and out.dns_ms is not None


def test_tls_hostname_mismatch_and_wildcard(tls_server: int) -> None:
    assert (
        checks_net.check_tls(tls_cfg(tls_server, sni="www.example.uz"), 5).detail["hostname_ok"]
        is True
    )  # wildcard
    other = checks_net.check_tls(tls_cfg(tls_server, sni="other.example.org"), 5)
    assert other.ok and other.detail["hostname_ok"] is False
    skipped = checks_net.check_tls(
        tls_cfg(tls_server, sni="x.org", check_hostname=False, check_chain=False), 5
    )
    assert skipped.detail["hostname_ok"] is None and skipped.detail["chain_ok"] is None


def test_tls_failures_and_ssrf(tls_server: int) -> None:
    assert (
        checks_net.check_tls({"host": "127.0.0.1", "port": tls_server}, 3).error_kind == "blocked"
    )
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
    refused = checks_net.check_tls(tls_cfg(dead), 6)  # Windows yopiq portda ~2 s kutadi
    assert not refused.ok and refused.error_kind in ("connect", "timeout")
    assert (
        checks_net.check_tls({"host": "no-such-host.invalid", "allow_private": True}, 3).error_kind
        == "dns"
    )
    # TLS emas, oddiy HTTP port
    plain = socket.socket()
    plain.bind(("127.0.0.1", 0))
    plain.listen(1)
    threading.Thread(
        target=lambda: plain.accept()[0].sendall(b"HTTP/1.1 400 Bad\r\n\r\n"), daemon=True
    ).start()
    garbage = checks_net.check_tls(tls_cfg(plain.getsockname()[1]), 3)
    plain.close()
    assert not garbage.ok and garbage.error_kind in ("tls", "connect")


def test_san_matches() -> None:
    sans = ["nazar.avlo.ai", "*.avlo.ai"]
    assert checks_net.san_matches("NAZAR.avlo.ai.", sans)
    assert checks_net.san_matches("app.avlo.ai", sans)
    assert not checks_net.san_matches("a.b.avlo.ai", sans)  # wildcard bitta daraja
    assert not checks_net.san_matches("avlo.ai", ["*.avlo.ai"])
    assert not checks_net.san_matches("evil.com", sans)


# ---------------------------------------------------------------- DNS (haqiqiy UDP DNS server)
@pytest.fixture
def dns_server() -> Iterator[tuple[str, int, dict[str, Any]]]:
    import dns.flags
    import dns.message
    import dns.rcode
    import dns.rrset

    table: dict[str, Any] = {"nazar.example.uz": ["164.68.105.194"]}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.2)
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except (TimeoutError, OSError):
                continue
            query = dns.message.from_wire(data)
            reply = dns.message.make_response(query)
            name = str(query.question[0].name).rstrip(".")
            answer = table.get(name)
            if answer is None:
                reply.set_rcode(dns.rcode.NXDOMAIN)
            else:
                reply.answer.append(
                    dns.rrset.from_text_list(query.question[0].name, 60, "IN", "A", answer)
                )
            sock.sendto(reply.to_wire(), addr)

    threading.Thread(target=loop, daemon=True).start()
    yield "127.0.0.1", sock.getsockname()[1], table
    stop.set()
    sock.close()


def test_dns_query_over_real_udp(
    dns_server: tuple[str, int, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import dns.resolver

    host, port, table = dns_server
    original = dns.resolver.Resolver

    class PortResolver(original):  # type: ignore[misc, valid-type]
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            self.port = port

    monkeypatch.setattr(dns.resolver, "Resolver", PortResolver)
    assert checks_net.dns_query(host, "nazar.example.uz", "A", 3)[:2] == (
        ["164.68.105.194"],
        "NOERROR",
    )
    assert checks_net.dns_query(host, "yoq.example.uz", "A", 3)[:2] == ([], "NXDOMAIN")
    table["multi.example.uz"] = ["2.2.2.2", "1.1.1.1"]
    assert checks_net.dns_query(host, "multi.example.uz", "A", 3)[0] == [
        "1.1.1.1",
        "2.2.2.2",
    ]  # saralangan
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]

    class DeadResolver(original):  # type: ignore[misc, valid-type]
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            self.port = dead

    monkeypatch.setattr(dns.resolver, "Resolver", DeadResolver)
    assert checks_net.dns_query(host, "nazar.example.uz", "A", 1)[1] in (
        "TIMEOUT",
        "ERROR",
        "SERVFAIL",
    )


class FakeDns:
    """checks_net.dns_query o'rniga: {(resolver, name): (javoblar, rcode)}."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, table: dict[str, tuple[list[str], str]]
    ) -> None:
        self.table = table
        monkeypatch.setattr(checks_net, "dns_query", self.query)

    def query(
        self, resolver: str, name: str, rtype: str, timeout: float
    ) -> tuple[list[str], str, int]:
        answers, rcode = self.table.get(resolver, ([], "TIMEOUT"))
        return answers, rcode, 12


def dns_cfg(**extra: Any) -> dict[str, Any]:
    return {
        "name": "nazar.avlo.ai",
        "expected": ["164.68.105.194"],
        "retired_ips": ["34.173.220.247"],
        **extra,
    }


def test_dns_all_resolvers_match(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = (["164.68.105.194"], "NOERROR")
    FakeDns(monkeypatch, {"8.8.8.8": ok, "1.1.1.1": ok, "9.9.9.9": ok})
    out = checks_net.check_dns(dns_cfg(), 3)
    assert out.ok and out.detail["retired"] == [] and len(out.detail["resolvers"]) == 3


def test_dns_mismatch_retired_and_nxdomain(monkeypatch: pytest.MonkeyPatch) -> None:
    good, retired = (["164.68.105.194"], "NOERROR"), (["34.173.220.247"], "NOERROR")
    FakeDns(monkeypatch, {"8.8.8.8": good, "1.1.1.1": retired, "9.9.9.9": good})
    out = checks_net.check_dns(dns_cfg(), 3)
    assert (
        not out.ok and out.error_kind == "mismatch" and out.detail["retired"] == ["34.173.220.247"]
    )
    bad = {r["resolver"]: r["matches"] for r in out.detail["resolvers"]}
    assert bad == {"8.8.8.8": True, "1.1.1.1": False, "9.9.9.9": True}
    FakeDns(monkeypatch, {ip: ([], "NXDOMAIN") for ip in ("8.8.8.8", "1.1.1.1", "9.9.9.9")})
    assert checks_net.check_dns(dns_cfg(), 3).error_kind == "nxdomain"


def test_dns_unresponsive_resolver_is_ignored_unless_all_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = (["164.68.105.194"], "NOERROR")
    FakeDns(monkeypatch, {"8.8.8.8": good, "9.9.9.9": good})  # 1.1.1.1 javob bermaydi
    assert checks_net.check_dns(dns_cfg(), 3).ok
    FakeDns(monkeypatch, {})
    out = checks_net.check_dns(dns_cfg(), 3)
    assert not out.ok and out.error_kind == "dns"  # hamma jim: DNS emas, tarmoq muammosi


def test_dns_without_expected_only_needs_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeDns(monkeypatch, {"8.8.8.8": (["1.2.3.4"], "NOERROR")})
    assert checks_net.check_dns({"name": "x.uz", "resolvers": ["8.8.8.8"]}, 3).ok


def test_dns_private_resolver_blocked_and_ns_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeDns(monkeypatch, {})
    out = checks_net.check_dns({"name": "x.uz", "resolvers": ["10.0.0.1"]}, 3)
    assert out.detail["resolvers"][0]["rcode"] == "BLOCKED" and not out.ok

    def fake(resolver: str, name: str, rtype: str, timeout: float) -> tuple[list[str], str, int]:
        if rtype == "NS":
            return ["ns1.example.uz."], "NOERROR", 1
        if name == "ns1.example.uz":
            return ["10.9.9.9", "93.184.216.34"], "NOERROR", 1  # ichki NS o'tkazib yuboriladi
        return (["1.2.3.4"], "NOERROR", 5) if resolver == "93.184.216.34" else ([], "TIMEOUT", 1)

    monkeypatch.setattr(checks_net, "dns_query", fake)
    assert checks_net.authoritative_ns("x.uz", 3) == "93.184.216.34"
    out = checks_net.check_dns(
        {"name": "x.uz", "expected": ["1.2.3.4"], "resolvers": ["ns:auto"]}, 3
    )
    assert out.ok and out.detail["resolvers"][0]["resolver"] == "ns:auto"


# ---------------------------------------------------------------- konfiguratsiya
@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("tls", {"port": 443}),
        ("tls", {"host": "x.uz", "port": 0}),
        ("tls", {"host": "x.uz", "warn_days": -1}),
        ("tls", {"host": "x.uz", "bilinmaydi": 1}),
        ("tls", {"host": "x.uz", "check_chain": "ha"}),
        ("dns", {"name": "yolg'on"}),
        ("dns", {"name": "x.uz", "rtype": "MX"}),
        ("dns", {"name": "x.uz", "resolvers": ["salom"]}),
        ("dns", {"name": "x.uz", "resolvers": ["10.0.0.1"]}),
        ("dns", {"name": "x.uz", "expected": ["yomon"]}),
        ("dns", {"name": "x.uz", "mismatch_after_min": 0}),
        ("dns", {"name": "x.uz", "resolvers": ["8.8.8.8"] * 7}),
    ],
)
def test_invalid_tls_dns_configs(kind: str, config: dict[str, Any]) -> None:
    with pytest.raises(services.ProbeConfigError):
        services.validate_config(kind, config)


def test_valid_tls_dns_configs() -> None:
    services.validate_config(
        "tls",
        {
            "host": "nazar.avlo.ai",
            "port": 443,
            "sni": "nazar.avlo.ai",
            "warn_days": 21,
            "check_chain": True,
        },
    )
    services.validate_config(
        "dns",
        {
            "name": "nazar.avlo.ai",
            "resolvers": ["8.8.8.8", "ns:auto"],
            "expected": ["1.2.3.4"],
            "mismatch_after_min": 10,
        },
    )


# ---------------------------------------------------------------- saqlash va avto-tekshiruvlar
def test_tls_outcome_upserts_cert_status() -> None:
    p = Project.objects.create(slug="n-1", name="N", kind="static")
    d = Domain.objects.create(fqdn="n.example.uz", project=p)
    probe = Probe.objects.create(
        project=p, domain=d, type="tls", name="n TLS", config={"host": "n.example.uz"}
    )
    detail = {
        "not_after": (timezone.now() + timedelta(days=30)).isoformat(), "days_left": 29, "issuer": "CN=R3",
        "subject": "CN=n.example.uz", "san": ["n.example.uz"], "chain_ok": True, "hostname_ok": True,
    }  # fmt: skip
    now = timezone.now()
    services.apply_outcome(probe, checks.Outcome(True, detail=detail), now)
    services.apply_outcome(
        probe, checks.Outcome(True, detail={**detail, "issuer": "CN=Yangi CA"}), now
    )  # yangilanish
    cert = CertStatus.objects.get()
    assert (
        cert.name == "n.example.uz"
        and cert.issuer == "CN=Yangi CA"
        and cert.domain == d
        and cert.source == "probe"
    )
    services.apply_outcome(probe, checks.Outcome(False, error_kind="timeout"), now)
    assert CertStatus.objects.count() == 1  # xato eski holatni o'chirmaydi


def test_dns_results_history_and_change_log() -> None:
    p = Project.objects.create(slug="n-1", name="N", kind="static")
    d = Domain.objects.create(fqdn="n.example.uz", project=p, expected_ips=["164.68.105.194"])
    probe = Probe.objects.create(
        project=p, domain=d, type="dns", name="n DNS", config=dns_cfg(name="n.example.uz")
    )

    def outcome(answers: list[str], rcode: str = "NOERROR") -> checks.Outcome:
        return checks.Outcome(
            answers == ["164.68.105.194"],
            detail={
                "resolvers": [
                    {
                        "resolver": "8.8.8.8",
                        "answers": answers,
                        "matches": answers == ["164.68.105.194"],
                        "rcode": rcode,
                        "latency_ms": 9,
                    }
                ],
                "retired": [],
            },
        )

    now = timezone.now()
    services.apply_outcome(
        probe, outcome(["34.173.220.247"]), now
    )  # birinchi natija: tarixda o'zgarish yo'q
    assert DnsChange.objects.count() == 0
    services.apply_outcome(probe, outcome(["34.173.220.247"]), now + timedelta(minutes=1))
    assert DnsChange.objects.count() == 0  # o'zgarmadi
    services.apply_outcome(probe, outcome(["164.68.105.194"]), now + timedelta(minutes=2))
    change = DnsChange.objects.get()
    assert (change.old_answers, change.new_answers, change.resolver) == (
        ["34.173.220.247"],
        ["164.68.105.194"],
        "8.8.8.8",
    )
    services.apply_outcome(probe, outcome([], "TIMEOUT"), now + timedelta(minutes=3))
    assert DnsChange.objects.count() == 1  # javob yo'q — o'zgarish emas


def test_auto_probes_include_tls_and_dns_when_expected_ips_known() -> None:
    Setting.objects.create(key="retired_ips", value=["34.173.220.247"])
    p = Project.objects.create(slug="n-1", name="N", kind="static")
    d = Domain.objects.create(fqdn="n.example.uz", project=p, expected_ips=["164.68.105.194"])
    assert {x.type for x in services.ensure_domain_probes(d)} == {"http", "tls", "dns"}
    dns = Probe.objects.get(type="dns")
    assert dns.config["expected"] == ["164.68.105.194"] and dns.config["retired_ips"] == [
        "34.173.220.247"
    ]
    assert dns.config["resolvers"] == ["8.8.8.8", "1.1.1.1", "9.9.9.9", "ns:auto"]
    off = Domain.objects.create(fqdn="off.example.uz", project=p, tls_enabled=False)
    assert {x.type for x in services.ensure_domain_probes(off)} == {"http"}


def test_sync_dns_probe_follows_expected_ips() -> None:
    d = Domain.objects.create(fqdn="n.example.uz")
    assert services.sync_dns_probe(d) is None
    d.expected_ips = ["1.1.1.1"]
    d.save()
    probe = services.sync_dns_probe(d)
    assert probe is not None
    Probe.objects.filter(pk=probe.pk).update(state="down", consecutive_failures=3)
    d.expected_ips = ["2.2.2.2"]
    d.save()
    again = services.sync_dns_probe(d)
    assert again is not None and again.pk == probe.pk and again.config["expected"] == ["2.2.2.2"]
    assert (
        again.state == "unknown" and again.consecutive_failures == 0
    )  # yangi kutilma: qaytadan boshlanadi
    d.expected_ips = []
    d.save()
    assert services.sync_dns_probe(d) is None
    assert Probe.objects.get().enabled is False


def test_domain_patch_syncs_dns_probe() -> None:
    make_user("operator", "operator")
    c = csrf_client()
    login(c, "operator")
    import json

    p = Project.objects.create(slug="n-1", name="N", kind="static")
    d = Domain.objects.create(fqdn="n.example.uz", project=p)
    r = c.patch(
        f"/api/v1/domains/{d.pk}",
        data=json.dumps({"expected_ips": ["164.68.105.194"]}),
        content_type="application/json",
        headers=csrf_headers(c),
    )
    assert r.status_code == 200
    assert Probe.objects.get(type="dns").config["expected"] == ["164.68.105.194"]


# ---------------------------------------------------------------- alert qoidalari: sertifikat
@pytest.fixture(autouse=True)
def _rules(db: None) -> None:
    sync_built_in()


def cert_domain(
    days: int, *, name: str = "nazar.avlo.ai", moved: bool = True, **status: Any
) -> CertStatus:
    project, _ = Project.objects.get_or_create(
        slug="nazar", defaults={"name": "Nazar", "kind": "compose", "moved": moved}
    )
    domain, _ = Domain.objects.get_or_create(fqdn=name, defaults={"project": project})
    return CertStatus.objects.create(
        domain=domain, name=name, source="probe", not_after=T0 + timedelta(days=days, hours=1),
        chain_ok=status.pop("chain_ok", True), hostname_ok=status.pop("hostname_ok", True),
        checked_at=status.pop("checked_at", T0),
    )  # fmt: skip


def cert_rules() -> None:
    only("AL-057", "AL-058", "AL-059", "AL-060")


def test_certificate_ladder_only_most_severe_notifies() -> None:
    cert_rules()
    channel()
    cert_domain(2)  # 2 kun: 21, 7, 3 chegaralarining hammasi rost
    run_cycle(T0)
    firing = {i.rule.key for i in AlertInstance.objects.filter(state="firing")}
    assert firing == {"AL-057", "AL-058", "AL-059"}
    (n,) = Notification.objects.all()
    assert (
        "🔴 <b>Sertifikat 3 kunda tugaydi" in n.payload["text"]
        and "2 kun qoldi" in n.payload["text"]
    )
    assert Incident.objects.get().severity == "critical"


@pytest.mark.parametrize(
    ("days", "expected"),
    [(25, set()), (15, {"AL-057"}), (5, {"AL-057", "AL-058"}), (0, {"AL-057", "AL-058", "AL-059"})],
)
def test_certificate_thresholds(days: int, expected: set[str]) -> None:
    cert_rules()
    cert_domain(days)
    run_cycle(T0)
    assert {i.rule.key for i in AlertInstance.objects.filter(state="firing")} == expected


def test_expired_certificate_message() -> None:
    cert_rules()
    channel()
    cert_domain(-4)
    run_cycle(T0)
    assert any(
        "muddati" in n.payload["text"] and "oldin tugagan" in n.payload["text"]
        for n in Notification.objects.all()
    )


def test_certificate_renewed_resolves() -> None:
    cert_rules()
    channel()
    cs = cert_domain(2)
    run_cycle(T0)
    CertStatus.objects.filter(pk=cs.pk).update(
        not_after=T0 + timedelta(days=80), checked_at=T0 + timedelta(minutes=5)
    )
    run_cycle(T0 + timedelta(minutes=5))
    run_cycle(T0 + timedelta(minutes=7))
    assert Incident.objects.get().status == "resolved"


def test_invalid_certificate_chain_or_hostname() -> None:
    cert_rules()
    channel()
    cert_domain(80, chain_ok=True, hostname_ok=False)
    run_cycle(T0)
    assert AlertInstance.objects.get(rule__key="AL-060").state == "pending"  # for=600
    run_cycle(T0 + timedelta(minutes=11))
    inst = AlertInstance.objects.get(rule__key="AL-060")
    assert inst.state == "firing" and "nom SAN ga mos emas" in inst.detail


def test_stale_unmoved_archived_certs_are_ignored() -> None:
    cert_rules()
    cs = cert_domain(1, checked_at=T0 - timedelta(days=5))  # tekshiruv to'xtagan
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()
    CertStatus.objects.filter(pk=cs.pk).update(checked_at=T0)
    Project.objects.update(moved=False)
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()
    Project.objects.update(moved=True)
    Domain.objects.update(status="archived")
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()


# ---------------------------------------------------------------- alert qoidalari: DNS
def dns_probe(*, state: str, since_min: int, retired: list[str] | None = None, **cfg: Any) -> Probe:
    project, _ = Project.objects.get_or_create(
        slug="nazar", defaults={"name": "Nazar", "kind": "compose"}
    )
    domain, _ = Domain.objects.get_or_create(fqdn="nazar.avlo.ai", defaults={"project": project})
    probe = Probe.objects.create(
        project=project, domain=domain, type="dns", name="nazar.avlo.ai DNS", state=state,
        state_since=T0 - timedelta(minutes=since_min), config=dns_cfg(**cfg),
    )  # fmt: skip
    detail = {
        "resolvers": [
            {
                "resolver": "1.1.1.1",
                "answers": ["9.9.9.9"],
                "matches": False,
                "rcode": "NOERROR",
                "latency_ms": 5,
            }
        ],
        "retired": retired or [],
    }
    services.store_result(probe, T0, checks.Outcome(state == "up", detail=detail))
    return probe


def test_dns_mismatch_alert_waits_mismatch_after_min() -> None:
    only("AL-062")
    channel()
    probe = dns_probe(state="down", since_min=4)  # 4 daqiqa < 10
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()
    Probe.objects.filter(pk=probe.pk).update(state_since=T0 - timedelta(minutes=11))
    run_cycle(T0 + timedelta(seconds=1))
    (n,) = Notification.objects.all()
    assert (
        "DNS kutilgan IP ga qaramaydi" in n.payload["text"]
        and "1.1.1.1 -&gt; 9.9.9.9" in n.payload["text"]
    )
    assert "kutilgan 164.68.105.194" in n.payload["text"]


def test_dns_mismatch_after_min_is_configurable_and_unknown_is_silent() -> None:
    only("AL-062")
    probe = dns_probe(state="down", since_min=4, mismatch_after_min=3)
    run_cycle(T0)
    assert AlertInstance.objects.get().state == "firing"
    Probe.objects.filter(pk=probe.pk).update(state="unknown")
    AlertInstance.objects.all().delete()
    run_cycle(T0)
    assert not AlertInstance.objects.filter(state="firing").exists()


def test_retired_ip_alert() -> None:
    only("AL-063")
    channel()
    dns_probe(state="down", since_min=1, retired=["34.173.220.247"])
    run_cycle(T0)
    run_cycle(T0 + timedelta(minutes=11))  # for=600
    (n,) = Notification.objects.all()
    assert "yopilgan IP ga qaraydi" in n.payload["text"] and "34.173.220.247" in n.payload["text"]


def test_dns_mismatch_suppresses_site_down_for_same_domain() -> None:
    only("AL-062", "AL-049")
    channel()
    dns_probe(state="down", since_min=20)
    project = Project.objects.get(slug="nazar")
    domain = Domain.objects.get(fqdn="nazar.avlo.ai")
    Probe.objects.create(
        project=project, domain=domain, type="http", name="nazar.avlo.ai HTTP", state="down",
        state_since=T0 - timedelta(minutes=20), config={"url": "https://nazar.avlo.ai/", "primary": True},
    )  # fmt: skip
    run_cycle(T0)
    by = {
        i.rule.key: i for i in AlertInstance.objects.select_related("rule").filter(state="firing")
    }
    assert by["AL-062"].suppressed is False and by["AL-049"].suppressed is True
    assert len(Notification.objects.all()) == 1  # sabab bitta: bitta xabar


def test_dns_tls_probes_dont_trigger_site_down_rule() -> None:
    only("AL-049", "AL-049H")
    dns_probe(state="down", since_min=20)
    Probe.objects.create(type="tls", name="t", state="down", config={"host": "x.uz"})
    run_cycle(T0)
    assert not AlertInstance.objects.exists()  # AL-049 faqat http/tcp


# ---------------------------------------------------------------- alert qoidalari: docker
def container(
    server: Server,
    name: str,
    *,
    running: float,
    expected: float,
    at: Any,
    restarts: float | None = None,
) -> None:
    labels = {"container": name, "project": "nazar", "service": "web"}
    put(server, "docker_container_running", running, at, **labels)
    put(server, "docker_container_expected", expected, at, **labels)
    if restarts is not None:
        put(server, "docker_container_restarts_total", restarts, at, **labels)


def test_expected_container_down_alerts_after_90s_and_unexpected_never() -> None:
    only("AL-035")
    channel()
    s = new_server()
    for at in [T0, T0 + timedelta(seconds=60), T0 + timedelta(seconds=100)]:
        container(s, "nazar-web-1", running=0, expected=1, at=at)
        container(s, "migrate-1", running=0, expected=0, at=at)  # bir martalik: kutilgan emas
        alive(s, at)
        run_cycle(at)
    firing = AlertInstance.objects.filter(state="firing")
    assert [i.subject_name for i in firing] == ["main-2 (nazar-web-1)"]
    (n,) = Notification.objects.all()
    assert "Konteyner ishlamayapti" in n.payload["text"] and "nazar-web-1" in n.payload["text"]
    # qaytib keldi
    for at in (T0 + timedelta(seconds=115), T0 + timedelta(seconds=200)):
        container(s, "nazar-web-1", running=1, expected=1, at=at)
        alive(s, at)
        run_cycle(at)
    assert Incident.objects.get().status == "resolved"


def test_crash_loop_detected_by_restart_counter() -> None:
    only("AL-036")
    channel()
    s = new_server()
    for i, restarts in enumerate([0, 1, 2, 3]):  # 10 daqiqada 3 marta
        at = T0 + timedelta(minutes=i)
        container(s, "nazar-web-1", running=1, expected=1, at=at, restarts=restarts)
        alive(s, at)
        run_cycle(at)
    inst = AlertInstance.objects.get(rule__key="AL-036")
    assert (
        inst.state == "firing"
        and "crash loop" in Notification.objects.get().payload["text"].lower()
    )


def test_when_condition_validation() -> None:
    base = {"type": "threshold", "metric": "docker_container_running", "op": "==", "value": 0}
    validate_condition(
        {**base, "when": {"metric": "docker_container_expected", "op": "==", "value": 1}}
    )
    for bad in (
        {"metric": "x", "op": "==", "value": 1, "extra": 1},
        {"metric": "X", "op": "==", "value": 1},
        {"metric": "x", "op": "~", "value": 1},
        "text",
    ):
        with pytest.raises(ConditionError):
            validate_condition({**base, "when": bad})


def test_new_state_source_validation() -> None:
    validate_condition({"type": "state", "source": "cert", "field": "days_left_lte", "equals": 7})
    validate_condition({"type": "state", "source": "dns", "field": "retired", "equals": True})
    for bad in (
        {"type": "state", "source": "cert", "field": "days_left_lte", "equals": True},
        {"type": "state", "source": "cert", "field": "days_left_lte", "equals": -1},
        {"type": "state", "source": "cert", "field": "days_left_lte", "equals": 99999},
        {"type": "state", "source": "dns", "field": "mismatch", "equals": "ha"},
        {"type": "state", "source": "probe", "field": "state", "equals": "down", "primary": "ha"},
    ):
        with pytest.raises(ConditionError):
            validate_condition(bad)


def test_all_builtin_rules_still_valid_and_enabled() -> None:
    for rule in AlertRule.objects.filter(built_in=True):
        validate_condition(rule.condition)
    assert {"AL-035", "AL-036", "AL-057", "AL-058", "AL-059", "AL-060", "AL-062", "AL-063"} <= set(
        AlertRule.objects.values_list("key", flat=True)
    )
    assert conditions.FANOUT_TYPES  # modul import qilinadi


# ---------------------------------------------------------------- API
def test_certs_and_dns_endpoints() -> None:
    make_user("kuzatuvchi", "viewer")
    viewer = csrf_client()
    login(viewer, "kuzatuvchi")
    now = timezone.now()
    p = Project.objects.create(slug="nazar", name="Nazar", kind="compose")
    d = Domain.objects.create(fqdn="nazar.avlo.ai", project=p)
    CertStatus.objects.create(
        domain=d,
        name="nazar.avlo.ai",
        source="probe",
        not_after=now + timedelta(days=15, hours=1),
        issuer="CN=R3",
        chain_ok=True,
        hostname_ok=True,
    )
    CertStatus.objects.create(name="eski.uz", source="probe", not_after=now + timedelta(days=200))
    items = viewer.get("/api/v1/certs/").json()["items"]
    assert (
        [i["name"] for i in items] == ["nazar.avlo.ai", "eski.uz"]
        and items[0]["days_left"] == 15
        and items[0]["project"] == "nazar"
    )
    assert [i["name"] for i in viewer.get("/api/v1/certs/?days_left_lt=21").json()["items"]] == [
        "nazar.avlo.ai"
    ]
    assert viewer.get("/api/v1/certs/?days_left_lt=abc").status_code == 400
    assert Client().get("/api/v1/certs/").status_code in (401, 403)

    probe = Probe.objects.create(project=p, domain=d, type="dns", name="dns", config=dns_cfg())
    for t, answers in ((now - timedelta(minutes=5), ["34.173.220.247"]), (now, ["164.68.105.194"])):
        services.apply_outcome(
            probe,
            checks.Outcome(
                answers == ["164.68.105.194"],
                detail={
                    "resolvers": [
                        {
                            "resolver": "8.8.8.8",
                            "answers": answers,
                            "matches": answers == ["164.68.105.194"],
                            "rcode": "NOERROR",
                            "latency_ms": 7,
                        }
                    ],
                    "retired": [],
                },
            ),
            t,
        )
    body = viewer.get(f"/api/v1/domains/{d.pk}/dns").json()
    assert body["resolvers"][0]["resolver"] == "8.8.8.8" and body["resolvers"][0]["answers"] == [
        "164.68.105.194"
    ]
    assert body["changes"][0]["old_answers"] == ["34.173.220.247"] and body["changes"][0][
        "new_answers"
    ] == ["164.68.105.194"]
    assert viewer.get("/api/v1/domains/00000000-0000-7000-8000-000000000000/dns").status_code == 404
