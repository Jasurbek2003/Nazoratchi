"""Xabar shablonlari (TZ 12.9, FR-NTF-003): ahamiyat belgisi + sarlavha, tafsilotlar, runbook, havola.
Telegram HTML rejimi: hamma o'zgaruvchan matn (server nomi, log satri) ekranlanadi.
"""

from dataclasses import dataclass, field
from html import escape
from typing import Any

from django.conf import settings

MAX_LEN = 1000  # FR-NTF-003
ICONS = {"critical": "🔴", "high": "🟠", "warning": "🟡", "info": "🔵"}
RESOLVED_ICON = "✅"


@dataclass(frozen=True)
class Message:
    severity: str
    title: str
    lines: list[str] = field(default_factory=list)
    runbook: str = ""  # masalan: "RB-001 → provayder panelidan holatni tekshiring"
    path: str = ""  # panel yo'li: "/incidents/0193..."; PUBLIC_URL ga qo'shiladi
    link_label: str = "Incident"
    resolved: bool = False


def _link(path: str) -> str:
    return f"{settings.PUBLIC_URL}{path}" if path.startswith("/") else ""


def render(msg: Message) -> dict[str, Any]:
    """`{"text": ..., "buttons": [...]}` — Notification.payload ga to'g'ridan-to'g'ri yoziladi."""
    icon = RESOLVED_ICON if msg.resolved else ICONS.get(msg.severity, ICONS["info"])
    # Sarlavha cheklanadi: oxirida kesish `<b>` tegini buzmasligi uchun (Telegram buzuq HTML ni rad etadi).
    head = f"{icon} <b>{escape(msg.title[:150], quote=False)}</b>"
    link = _link(msg.path)
    tail: list[str] = []
    if msg.runbook:
        tail.append(f"Nima qilish kerak: {escape(msg.runbook, quote=False)}")
    if link:
        tail.append(f"{escape(msg.link_label, quote=False)}: {escape(link, quote=False)}")

    # Sarlavha va oxiri (runbook, havola) doim qoladi; uzun bo'lsa o'rtadagi satrlar qisqartiriladi.
    fixed = len(head) + sum(len(t) + 1 for t in tail) + 4
    budget = MAX_LEN - fixed
    body: list[str] = []
    for raw in msg.lines:
        line = escape(raw, quote=False)
        if len(line) + 1 > budget:
            line = line[: max(0, budget - 2)] + "…" if budget > 2 else ""
            if line:
                body.append(line)
            break
        body.append(line)
        budget -= len(line) + 1
    parts = [head]
    if body:
        parts.append("\n".join(body))
    if tail:
        parts.append("\n".join(tail))
    text = "\n\n".join(parts)
    buttons = [{"text": "Panelda ochish", "url": link}] if link else []
    return {"text": text[:MAX_LEN], "buttons": buttons}


def channel_test_message(channel_name: str) -> Message:
    """Panel tugmasi bilan kanalni tekshirish (FR-ALR-020)."""
    return Message(
        severity="info",
        title="Nazoratchi: sinov xabari",
        lines=[
            f"Kanal: {channel_name}",
            "Agar shu xabarni ko'rayotgan bo'lsangiz, kanal ishlayapti.",
        ],
        path="/",
        link_label="Panel",
    )
