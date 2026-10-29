"""Agentni yangilash (FR-AGT-008, TZ 7.7.3): Owner so'raydi, core `update` buyrug'ini ingest javobiga qo'shadi.

Core faqat maslahat beradi. Agent faylni yuklaydi va **imzolangan** `SHA256SUMS` dan versiya, xesh va imzoni
mustaqil tekshiradi; core noto'g'ri versiya yoki xesh bildirsa agent rad etadi (14.5.4).
"""

from apps.core.dist import latest_agent_version, parse_version, update_command

from .models import HostEvent, Server

Version = tuple[int, int, int]


def fmt(version: Version) -> str:
    return ".".join(str(p) for p in version)


def reported_version(server: Server) -> Version | None:
    """Agent `X-Nazoratchi-Agent: nazoratchi-agent/1.2.3` sarlavhasida bildirgan versiya."""
    return parse_version(server.agent_version) if server.agent_version else None


def request_update(server: Server) -> tuple[str | None, str | None]:
    """So'rovni qayd etadi. Qaytadi: (nishon versiya, rad etish sababi)."""
    current = reported_version(server)
    if current is None:
        return None, "Agent versiyasi noma'lum yoki reliz emas (dev): masofadan yangilab bo'lmaydi."
    if str(server.facts.get("arch", "")) not in ("amd64", "arm64"):
        return None, "Agent arxitekturasi noma'lum (hali fakt yubormagan)."
    latest = latest_agent_version()
    if latest is None or update_command(str(server.facts["arch"])) is None:
        return None, "Core'da agent reliz fayllari (VERSION, SHA256SUMS) yo'q."
    target = parse_version(latest)
    if target is None or target <= current:  # latest_agent_version() formatni kafolatlaydi
        return None, f"Agent allaqachon eng yangi versiyada ({fmt(current)})."
    return latest, None


def on_ingest(server: Server, previous_version: str) -> list[dict[str, str]]:
    """Har ingestda chaqiriladi: versiya o'zgarishini qayd etadi va kerak bo'lsa `update` buyrug'ini qaytaradi."""
    current = reported_version(server)
    before = parse_version(previous_version) if previous_version else None
    if current is not None and before is not None and current != before:
        HostEvent.objects.create(
            server=server,
            type="agent_updated" if current > before else "agent_downgraded",
            data={
                "from": fmt(before),
                "to": fmt(current),
                "requested": bool(server.agent_update_to),
            },
        )

    if not server.agent_update_to:
        return []
    target = parse_version(server.agent_update_to)
    if target is None or current is None or current >= target:
        server.agent_update_to = ""  # maqsadga yetildi (yoki yaroqsiz): so'rov yakunlandi
        server.save(update_fields=["agent_update_to"])
        return []
    command = update_command(str(server.facts.get("arch", "")))
    latest = parse_version(command["version"]) if command else None
    if command is None or latest is None or latest <= current:
        return []
    return [command]
