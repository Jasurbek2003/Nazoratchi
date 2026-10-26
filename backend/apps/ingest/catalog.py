"""Metrika katalogi qoidalari (TZ 7.3, 7.4): nom, belgilar, diapazon, agregat darajasi."""

import re

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")

# TZ 7.3.1: ruxsat etilgan belgilar (labels). URL, foydalanuvchi ID, IP kabi har safar yangi
# qiymat chiqaradigan belgilar taqiqlanadi (kardinallik).
ALLOWED_LABELS = frozenset(
    {
        "device",
        "mount",
        "iface",
        "container",
        "project",
        "service",
        "unit",
        "core",
        "mode",
        "name",
        "kind",
        "fstype",
        "job",
        "collector",
        "rank",
        "version",
    }
)

MAX_LABEL_VALUE_LEN = 200
MAX_SERIES_PER_HOST = 1000  # TZ 7.3.1: oshsa namuna rad etiladi
MAX_BODY_BYTES = 1_048_576  # TZ 7.5.2: > 1 MB -> 413
MAX_CLOCK_SKEW_S = (
    600  # |sent_at - core vaqti| > 10 daqiqa -> agent soati siljigan, paket vaqti tuzatiladi
)
MAX_SAMPLE_AGE_S = (
    3600  # undan eski namuna yozilmaydi: siqilgan bo'laklarga yozuv dublikat beradi (R-102)
)
MAX_FUTURE_S = 60

# R-102 / TZ 8.4.2: agregat darajalarda saqlanadigan "muhim" metrikalar (hajm ~3 baravar kam).
ROLLUP_METRICS = frozenset(
    {
        "cpu_busy_percent",
        "load1",
        "load5",
        "load15",
        "mem_used_percent",
        "swap_used_percent",
        "fs_used_percent",
        "net_rx_bytes_per_sec",
        "net_tx_bytes_per_sec",
    }
)

_UNIT_BY_SUFFIX = (
    ("_percent", "%"),
    ("_bytes", "bayt"),
    ("_per_sec", "1/s"),
    ("_seconds", "s"),
)


def unit_for(name: str) -> str:
    for suffix, unit in _UNIT_BY_SUFFIX:
        if name.endswith(suffix):
            return unit
    return ""


def kind_for(name: str) -> str:
    return "counter" if name.endswith("_total") else "gauge"


def value_in_range(name: str, value: float) -> bool:
    """Foizli metrikalar 0..100 oralig'ida bo'lishi kerak (TZ 14.5.5, T-U-ING-05)."""
    if name.endswith("_percent"):
        return 0.0 <= value <= 100.0
    return True
