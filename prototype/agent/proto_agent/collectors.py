"""Metrika kollektorlari (TZ 7.4): system, disk, net. Nomlar katalogga mos."""

import platform
import time
from collections.abc import Callable
from typing import Any

import psutil

Sample = dict[str, Any]

# TZ 7.4.3: standart bo'yicha yashiriladigan interfeyslar.
_IGNORED_IFACE_PREFIXES = ("lo", "veth", "br-", "docker", "Loopback", "isatap", "Teredo")
_IGNORED_FSTYPES = {"tmpfs", "overlay", "squashfs", "devtmpfs", "proc", "sysfs", "cgroup", ""}


def _pct(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


class Collector:
    def __init__(
        self,
        net_counters: Callable[[], dict[str, tuple[int, int]]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._net_counters = net_counters or self._psutil_net
        self._clock = clock
        self._prev_net: dict[str, tuple[float, int, int]] = {}
        # Birinchi chaqiruv 0.0 qaytaradi; hisoblagichni boshlaydi.
        psutil.cpu_percent(interval=None)

    @staticmethod
    def _psutil_net() -> dict[str, tuple[int, int]]:
        return {
            name: (c.bytes_recv, c.bytes_sent)
            for name, c in psutil.net_io_counters(pernic=True).items()
        }

    def collect(self, now_ms: int | None = None) -> list[Sample]:
        t = now_ms if now_ms is not None else int(time.time() * 1000)
        out: list[Sample] = []

        def add(name: str, value: float, **labels: str) -> None:
            out.append({"n": name, "t": t, "v": float(value), "l": labels})

        # --- system ---
        add("cpu_busy_percent", _pct(psutil.cpu_percent(interval=None)))
        load1, load5, load15 = psutil.getloadavg()
        add("load1", load1)
        add("load5", load5)
        add("load15", load15)
        mem = psutil.virtual_memory()
        add("mem_total_bytes", mem.total)
        add("mem_available_bytes", mem.available)
        add("mem_used_bytes", mem.total - mem.available)
        add("mem_used_percent", _pct(100.0 * (mem.total - mem.available) / mem.total))
        swap = psutil.swap_memory()
        add("swap_used_percent", _pct(swap.percent) if swap.total else 0.0)
        add("boot_time_seconds", psutil.boot_time())
        add("uptime_seconds", max(0.0, time.time() - psutil.boot_time()))

        # --- disk ---
        for part in psutil.disk_partitions(all=False):
            if part.fstype in _IGNORED_FSTYPES or "cdrom" in part.opts:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            add(
                "fs_used_percent",
                _pct(usage.percent),
                mount=part.mountpoint,
                device=part.device,
                fstype=part.fstype,
            )

        # --- net (tezlik: ikki o'lchov farqi / vaqt) ---
        mono = self._clock()
        for iface, (rx, tx) in self._net_counters().items():
            if iface.startswith(_IGNORED_IFACE_PREFIXES):
                continue
            prev = self._prev_net.get(iface)
            self._prev_net[iface] = (mono, rx, tx)
            if prev is None or mono <= prev[0]:
                continue
            dt = mono - prev[0]
            # Hisoblagich qayta boshlansa (kamaysa) manfiy tezlik bo'lmasin (T-U-AGT-06).
            add("net_rx_bytes_per_sec", max(0, rx - prev[1]) / dt, iface=iface)
            add("net_tx_bytes_per_sec", max(0, tx - prev[2]) / dt, iface=iface)
        return out


def host_facts() -> dict[str, Any]:
    uname = platform.uname()
    return {
        "hostname": uname.node,
        "os": platform.platform(),
        "kernel_running": uname.release,
        "arch": platform.machine(),
        "cpu_count": psutil.cpu_count(logical=True),
        "mem_total_bytes": psutil.virtual_memory().total,
    }
