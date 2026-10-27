"""Standart qoidalar (TZ 12.7, FR-ALR-006). S3 da yig'ilayotgan ma'lumotga tayanadigan F1 qoidalari;
docker, tekshiruv (probe), sertifikat, DNS va zaxira qoidalari ularning ma'lumoti paydo bo'lgan sprintda qo'shiladi.

Qoida bazada yo'q bo'lsa yaratiladi; mavjud qoidaga TEGILMAYDI (foydalanuvchi chegarani o'zgartirgan bo'lishi mumkin).
"""

from typing import Any

from .models import AlertRule

HOST = {"type": "host"}


def _threshold(metric: str, op: str, value: float, **extra: Any) -> dict[str, Any]:
    return {
        "type": "threshold",
        "metric": metric,
        "op": op,
        "value": value,
        "aggregate": "last",
        "window_s": 60,
        **extra,
    }


_SILENT = {"type": "absent", "metric": "agent_up", "max_age_s": 120}

BUILT_IN: list[dict[str, Any]] = [
    {
        "key": "AL-001", "name": "Server o'chdi", "scope": HOST, "for_seconds": 0, "severity": "critical",
        "condition": {"type": "and", "of": [_SILENT, {"type": "state", "source": "reachability", "field": "tcp22", "equals": "down"}]},
        "runbook_key": "RB-001", "runbook_hint": "provayder panelidan holatni tekshiring (VNC/Rescue)",
    },
    {
        "key": "AL-002", "name": "Agent javob bermayapti", "scope": HOST, "for_seconds": 180, "severity": "high",
        "condition": {"type": "and", "of": [_SILENT, {"type": "state", "source": "reachability", "field": "tcp22", "equals": "up"}]},
        "runbook_key": "RB-002", "runbook_hint": "serverda `systemctl status nazoratchi-agent` va logni tekshiring",
    },
    {
        "key": "AL-003", "name": "Kutilmagan reboot", "scope": HOST, "for_seconds": 0, "severity": "high",
        "condition": {"type": "rate", "metric": "boot_time_seconds", "increase": 1, "window_s": 600},
        "runbook_key": "RB-003", "runbook_hint": "reboot sababini aniqlang (`last -x`, `journalctl -b -1`)",
    },
    {
        "key": "AL-008", "name": "Ko'p host jim (core tarmog'i)", "scope": {"type": "system"}, "for_seconds": 0, "severity": "critical",
        "condition": {"type": "state", "source": "fleet", "field": "mass_silent", "equals": True},
        "runbook_key": "RB-012", "runbook_hint": "avval Nazoratchi serverining tarmog'ini tekshiring (sabab shu tomonda bo'lishi mumkin)",
    },
    {
        "key": "AL-009", "name": "CPU yuqori", "scope": HOST, "for_seconds": 600, "severity": "warning",
        "condition": _threshold("cpu_busy_percent", ">", 90),
        "runbook_key": "RB-009", "runbook_hint": "`top`/`docker stats` bilan eng og'ir jarayonni toping",
    },
    {
        "key": "AL-014", "name": "RAM yuqori", "scope": HOST, "for_seconds": 600, "severity": "warning",
        "condition": _threshold("mem_used_percent", ">", 90),
        "runbook_key": "RB-010", "runbook_hint": "`free -h`, `docker stats`; xotira oqishini tekshiring",
    },
    {
        "key": "AL-015", "name": "RAM kritik", "scope": HOST, "for_seconds": 300, "severity": "critical",
        "condition": _threshold("mem_used_percent", ">", 96),
        "runbook_key": "RB-010", "runbook_hint": "OOM xavfi: og'ir jarayonni to'xtating yoki xotirani oshiring",
    },
    {
        "key": "AL-019", "name": "Disk 80%", "scope": HOST, "for_seconds": 300, "severity": "warning",
        "condition": _threshold("fs_used_percent", ">", 80),
        "runbook_key": "RB-004", "runbook_hint": "`docker system df`, eski image/log/zaxiralarni tozalang",
    },
    {
        "key": "AL-020", "name": "Disk 90%", "scope": HOST, "for_seconds": 300, "severity": "high",
        "condition": _threshold("fs_used_percent", ">", 90),
        "runbook_key": "RB-004", "runbook_hint": "`docker system df`, eski image/log/zaxiralarni tozalang",
    },
    {
        "key": "AL-021", "name": "Disk 95%", "scope": HOST, "for_seconds": 120, "severity": "critical",
        "condition": _threshold("fs_used_percent", ">", 95),
        "runbook_key": "RB-004", "runbook_hint": "zudlik bilan joy bo'shating: disk to'lsa servislar to'xtaydi",
    },
    {
        "key": "AL-022", "name": "Disk 7 kunda to'ladi (bashorat)", "scope": HOST, "for_seconds": 1800, "severity": "warning",
        "condition": {"type": "forecast", "metric": "fs_used_bytes", "limit_metric": "fs_total_bytes", "horizon_s": 7 * 86400,
                      "fit_window_s": 6 * 3600, "min_r2": 0.5, "min_used_percent": 50},
        "runbook_key": "RB-004", "runbook_hint": "o'sish manbasini toping (`du -xh / | sort -h | tail`)",
    },
    {
        "key": "AL-023", "name": "Disk 24 soatda to'ladi (bashorat)", "scope": HOST, "for_seconds": 900, "severity": "critical",
        "condition": {"type": "forecast", "metric": "fs_used_bytes", "limit_metric": "fs_total_bytes", "horizon_s": 86400,
                      "fit_window_s": 6 * 3600, "min_r2": 0.5, "min_used_percent": 50},
        "runbook_key": "RB-004", "runbook_hint": "zudlik bilan o'sish manbasini toping va joy bo'shating",
    },
    {
        "key": "AL-025", "name": "Fayl tizimi faqat o'qish rejimida", "scope": HOST, "for_seconds": 60, "severity": "critical",
        "condition": _threshold("fs_readonly", "==", 1),
        "runbook_key": "RB-005", "runbook_hint": "disk xatosi: `dmesg | tail`, provayderga murojaat qiling",
    },
    {
        "key": "AL-047", "name": "Heartbeat kelmadi", "scope": {"type": "job"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "heartbeat_job", "field": "overdue", "equals": True},
        "runbook_key": "RB-024", "runbook_hint": "cron/skript ishlayaptimi? `appctl heartbeat ok` bilan qo'lda sinang",
    },
    {
        "key": "AL-048", "name": "Heartbeat \"xato\" dedi", "scope": {"type": "job"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "heartbeat_job", "field": "failed", "equals": True},
        "runbook_key": "RB-024", "runbook_hint": "skript logini ko'ring: u o'zi xato haqida xabar bergan",
    },
    {
        "key": "AL-086", "name": "Bildirishnoma kanali ishlamayapti", "scope": {"type": "channel"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "channel", "field": "failing", "equals": True},
        "runbook_key": "RB-041", "runbook_hint": "bot tokeni va chat ID ni tekshiring; bot bloklanmaganmi?",
    },
    {
        "key": "AL-049", "name": "Sayt ishlamayapti", "scope": {"type": "probe"}, "for_seconds": 0, "severity": "critical",
        "condition": {"type": "state", "source": "probe", "field": "state", "equals": "down", "primary": True},
        "runbook_key": "RB-025", "runbook_hint": "avval serverni (`docker ps`, nginx logi), keyin DNS va sertifikatni tekshiring",
    },
    {
        "key": "AL-049H", "name": "Sayt ishlamayapti (asosiy emas)", "scope": {"type": "probe"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "probe", "field": "state", "equals": "down", "primary": False},
        "runbook_key": "RB-025", "runbook_hint": "avval serverni (`docker ps`, nginx logi), keyin DNS va sertifikatni tekshiring",
    },
    {
        "key": "AL-035", "name": "Konteyner ishlamayapti", "scope": HOST, "for_seconds": 90, "severity": "high",
        "condition": {"type": "threshold", "metric": "docker_container_running", "op": "==", "value": 0, "aggregate": "last", "window_s": 60,
                      "when": {"metric": "docker_container_expected", "op": "==", "value": 1}},
        "runbook_key": "RB-020", "runbook_hint": "`docker ps -a`, `docker logs <konteyner>`; ataylab to'xtatilgan bo'lsa jim qiling",
    },
    {
        "key": "AL-036", "name": "Konteyner crash loop", "scope": HOST, "for_seconds": 0, "severity": "high",
        "condition": {"type": "rate", "metric": "docker_container_restarts_total", "increase": 2, "window_s": 600},
        "runbook_key": "RB-020", "runbook_hint": "`docker logs --tail 100 <konteyner>`: nega qayta-qayta yiqilmoqda?",
    },
    {
        "key": "AL-057", "name": "Sertifikat 21 kunda tugaydi", "scope": {"type": "cert"}, "for_seconds": 0, "severity": "warning",
        "condition": {"type": "state", "source": "cert", "field": "days_left_lte", "equals": 21},
        "runbook_key": "RB-006", "runbook_hint": "`certbot renew --dry-run`; yangilash cron/timer ishlayaptimi?",
    },
    {
        "key": "AL-058", "name": "Sertifikat 7 kunda tugaydi", "scope": {"type": "cert"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "cert", "field": "days_left_lte", "equals": 7},
        "runbook_key": "RB-006", "runbook_hint": "`certbot renew`; nginx reload qilinganini tekshiring",
    },
    {
        "key": "AL-059", "name": "Sertifikat 3 kunda tugaydi yoki tugadi", "scope": {"type": "cert"}, "for_seconds": 0, "severity": "critical",
        "condition": {"type": "state", "source": "cert", "field": "days_left_lte", "equals": 3},
        "runbook_key": "RB-006", "runbook_hint": "zudlik bilan yangilang: `certbot renew --force-renewal` va nginx reload",
    },
    {
        "key": "AL-060", "name": "Sertifikat yaroqsiz", "scope": {"type": "cert"}, "for_seconds": 600, "severity": "high",
        "condition": {"type": "state", "source": "cert", "field": "invalid", "equals": True},
        "runbook_key": "RB-006", "runbook_hint": "zanjir (fullchain.pem) to'liqmi va domen SAN da bormi?",
    },
    {
        "key": "AL-062", "name": "DNS kutilgan IP ga qaramaydi", "scope": {"type": "dns"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "dns", "field": "mismatch", "equals": True},
        "runbook_key": "RB-007", "runbook_hint": "DNS provayderida A yozuvini tekshiring; o'zgarish yaqinda bo'lsa tarqalishni kuting",
    },
    {
        "key": "AL-063", "name": "Domen yopilgan IP ga qaraydi", "scope": {"type": "dns"}, "for_seconds": 600, "severity": "high",
        "condition": {"type": "state", "source": "dns", "field": "retired", "equals": True},
        "runbook_key": "RB-007", "runbook_hint": "domen o'chirilgan serverga qaraydi: A yozuvini yangi IP ga o'zgartiring",
    },
    {
        "key": "AL-068", "name": "Zaxira kechikdi", "scope": {"type": "backup"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "backup", "field": "age_hours_gt", "equals": 26},
        "runbook_key": "RB-031", "runbook_hint": "`appctl backup <loyiha>` ni qo'lda ishga tushiring; cron va log (/var/log/appctl-backup.log) ni tekshiring",
    },
    {
        "key": "AL-069", "name": "Zaxira uzoq vaqt olinmadi", "scope": {"type": "backup"}, "for_seconds": 0, "severity": "critical",
        "condition": {"type": "state", "source": "backup", "field": "age_hours_gt", "equals": 50},
        "runbook_key": "RB-031", "runbook_hint": "ma'lumot yo'qolish xavfi: zaxirani zudlik bilan qo'lda oling va sababni toping",
    },
    {
        "key": "AL-070", "name": "Zaxira muvaffaqiyatsiz", "scope": {"type": "backup"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "backup", "field": "last_failed", "equals": True},
        "runbook_key": "RB-031", "runbook_hint": "`appctl backup <loyiha>` chiqishi va state.json dagi `error` ni ko'ring (dump, joy, ruxsat)",
    },
    {
        "key": "AL-071", "name": "Zaxira shubhali: juda kichik", "scope": {"type": "backup"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "backup", "field": "size_small", "equals": True},
        "runbook_key": "RB-032", "runbook_hint": "bo'sh yoki yarim dump bo'lishi mumkin: faylni oching (`gzip -t`, `zcat | head`) va bazani tekshiring",
    },
    {
        "key": "AL-072", "name": "Zaxira shubhali: juda katta", "scope": {"type": "backup"}, "for_seconds": 0, "severity": "info",
        "condition": {"type": "state", "source": "backup", "field": "size_large", "equals": True},
        "runbook_key": "RB-032", "runbook_hint": "hajm keskin o'sdi: ma'lumot yoki log jadvallari ko'paygan bo'lishi mumkin",
    },
    {
        "key": "AL-075", "name": "Offsite zaxira sozlanmagan", "scope": HOST, "for_seconds": 0, "severity": "warning",
        "condition": _threshold("backup_offsite_configured", "==", 0),
        "runbook_key": "RB-033", "runbook_hint": "appctl.conf da OFFSITE ni to'ldiring (S-00 dagi rrsync papkasi): zaxira faqat shu serverda",
    },
    {
        "key": "AL-090", "name": "Nazoratchi o'z zaxirasi eskirdi", "scope": {"type": "system"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "self_backup", "field": "age_hours_gt", "equals": 30},
        "runbook_key": "RB-044", "runbook_hint": "`manage.py self_backup` ni qo'lda ishga tushiring; owner-backup kanali, bot va age kalitini tekshiring",
    },
    {
        "key": "AL-091", "name": "Nazoratchi o'z zaxirasi yuborilmadi", "scope": {"type": "system"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "self_backup", "field": "failed", "equals": True},
        "runbook_key": "RB-044", "runbook_hint": "xato sababi yuqorida: kanal topilmadi, age kaliti yo'q yoki Telegram rad etdi",
    },
    {
        "key": "AL-085", "name": "Prober qotdi", "scope": {"type": "system"}, "for_seconds": 0, "severity": "high",
        "condition": {"type": "state", "source": "prober", "field": "stalled", "equals": True},
        "runbook_key": "RB-040", "runbook_hint": "`run_prober` jarayoni ishlayaptimi? loglarni tekshiring",
    },
]  # fmt: skip


def sync_built_in() -> int:
    """Yo'q standart qoidalarni yaratadi. Qaytadi: yaratilganlar soni. Mavjudlarga tegmaydi."""
    created = 0
    existing = set(
        AlertRule.objects.filter(key__in=[r["key"] for r in BUILT_IN]).values_list("key", flat=True)
    )
    for spec in BUILT_IN:
        if spec["key"] in existing:
            continue
        AlertRule.objects.create(built_in=True, enabled=True, **spec)
        created += 1
    return created
