#!/usr/bin/env python3
"""Yuklama simulyatori (TZ 16.5, 16.9): virtual agentlar haqiqiy paket hajmi bilan core'ga metrika yuboradi.

Faqat stdlib. Har virtual agent o'z tokeniga ega (`--tokens-file`, har qatorda bitta token) va har
`--interval` soniyada ~243 namunali gzip paket yuboradi. Oxirida kechikish (p50/p95/p99), xato foizi va
T-P-01/02 mezonlariga muvofiqlik chiqariladi. Chiqish kodi: mezon buzilsa 1.

Namuna:
    python tools/simulator/simulate.py --url http://127.0.0.1:8000 --tokens-file tokens.txt \\
        --duration 600 --interval 15 --pattern daily
"""

import argparse
import gzip
import json
import math
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

PATTERNS = ("steady", "daily", "spike", "sustained_high", "mem_leak", "disk_growth")
CORES = 4
MOUNTS = ["/", "/boot", "/var/lib/docker", "/data"]
IFACES = ["eth0", "eth1"]
CONTAINERS = [f"app-{i}" for i in range(12)]


def cpu_value(pattern: str, t: float, rng: random.Random) -> float:
    base = 12 + rng.uniform(-3, 3)
    if pattern == "daily":
        base += 20 * (0.5 + 0.5 * math.sin(2 * math.pi * (t % 86400) / 86400))
    elif pattern == "spike" and int(t) % 600 < 150:
        base = 95
    elif pattern == "sustained_high":
        base = 93
    return max(0.0, min(100.0, base))


def build_samples(
    pattern: str, t: float, rng: random.Random, started: float
) -> list[dict]:
    """~243 qator/host (TZ 7.4): tizim, disk, tarmoq, konteyner metrikalari."""
    ms = int(t * 1000)
    out: list[dict] = []

    def add(name: str, value: float, **labels: str) -> None:
        out.append({"n": name, "t": ms, "v": round(value, 3), "l": labels})

    cpu = cpu_value(pattern, t, rng)
    add("cpu_busy_percent", cpu)
    for mode in ("user", "system", "iowait", "steal", "nice", "irq", "softirq"):
        add("cpu_mode_percent", rng.uniform(0, cpu / 3), mode=mode)
    for core in range(CORES):
        add("cpu_core_percent", cpu + rng.uniform(-5, 5), core=str(core))
    for name in ("load1", "load5", "load15"):
        add(name, cpu / 25)
    mem = (
        55 + (t - started) / 3600 if pattern == "mem_leak" else 55 + rng.uniform(-2, 2)
    )
    add("mem_used_percent", min(99, mem))
    for name in ("mem_total_bytes", "mem_available_bytes", "swap_used_percent"):
        add(name, rng.uniform(1e9, 8e9) if "bytes" in name else rng.uniform(0, 5))
    for mount in MOUNTS:
        used = 40 + ((t - started) / 86400 * 2 if pattern == "disk_growth" else 0)
        for name, v in (
            ("fs_used_percent", used),
            ("fs_inodes_used_percent", rng.uniform(5, 20)),
            ("fs_total_bytes", 1e11),
            ("fs_free_bytes", 1e11 * (100 - used) / 100),
        ):
            add(name, v, mount=mount, device="/dev/sda1", fstype="ext4")
    for iface in IFACES:
        for name in (
            "net_rx_bytes_per_s",
            "net_tx_bytes_per_s",
            "net_rx_errors",
            "net_tx_errors",
            "net_rx_packets_per_s",
            "net_tx_packets_per_s",
            "net_rx_dropped",
            "net_tx_dropped",
        ):
            add(name, rng.uniform(0, 1e6), iface=iface)
    for c in CONTAINERS:
        for name in (
            "container_cpu_percent",
            "container_mem_bytes",
            "container_mem_percent",
            "container_restarts",
            "container_running",
            "container_net_rx_bytes_per_s",
            "container_net_tx_bytes_per_s",
            "container_pids",
            "container_uptime_s",
            "container_blk_read_bytes_per_s",
            "container_blk_write_bytes_per_s",
        ):
            add(
                name,
                rng.uniform(0, 100) if "percent" in name else rng.uniform(0, 1e6),
                container=c,
            )
    for name in (
        "uptime_s",
        "procs_total",
        "procs_running",
        "open_fds",
        "ctx_switches_per_s",
        "disk_read_bytes_per_s",
        "disk_write_bytes_per_s",
        "disk_io_util_percent",
    ):
        add(name, rng.uniform(0, 1000))
    return out


@dataclass
class Stats:
    lat_ms: list[float] = field(default_factory=list)
    codes: dict[int, int] = field(default_factory=dict)
    errors: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, code: int, ms: float) -> None:
        with self.lock:
            self.codes[code] = self.codes.get(code, 0) + 1
            if code == 200:
                self.lat_ms.append(ms)


def post(url: str, token: str, batch: dict, stats: Stats) -> None:
    body = gzip.compress(json.dumps(batch).encode())
    req = urllib.request.Request(
        url + "/ingest/v1/metrics",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "X-Nazoratchi-Agent": "simulator",
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
            stats.record(r.status, (time.perf_counter() - t0) * 1000)
    except urllib.error.HTTPError as e:
        stats.record(e.code, (time.perf_counter() - t0) * 1000)
    except Exception:
        with stats.lock:
            stats.errors += 1


def agent_loop(
    url: str, token: str, args: argparse.Namespace, stats: Stats, stop: float, seed: int
) -> None:
    rng = random.Random(seed)  # noqa: S311
    started = time.time()
    seq = 0
    time.sleep(rng.uniform(0, args.interval))  # agentlar bir vaqtda boshlamasin
    next_t = time.monotonic()
    while time.monotonic() < stop:
        seq += 1
        now = time.time()
        batch = {
            "batch_id": str(uuid.uuid4()),
            "seq": seq,
            "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "samples": build_samples(args.pattern, now, rng, started),
        }
        post(url, token, batch, stats)
        next_t += args.interval
        time.sleep(max(0.0, next_t - time.monotonic()))


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(len(s) - 1, int(math.ceil(q * len(s))) - 1)]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument(
        "--tokens-file", required=True, help="har qatorda bitta agent tokeni"
    )
    ap.add_argument(
        "--agents", type=int, default=0, help="0 = fayldagi barcha tokenlar"
    )
    ap.add_argument("--duration", type=float, default=60, help="soniya")
    ap.add_argument("--interval", type=float, default=15)
    ap.add_argument("--pattern", choices=PATTERNS, default="steady")
    ap.add_argument("--p95-ms", type=float, default=300, help="NFR-PRF-001")
    ap.add_argument("--p99-ms", type=float, default=1000)
    args = ap.parse_args()

    tokens = [
        t.strip() for t in Path(args.tokens_file).read_text().splitlines() if t.strip()
    ]
    if args.agents:
        tokens = tokens[: args.agents]
    if not tokens:
        print("token topilmadi", file=sys.stderr)
        return 2
    # Rate-limit (30/daq/token) bo'yicha interval juda kichik bo'lmasin.
    stats = Stats()
    stop = time.monotonic() + args.duration
    threads = [
        threading.Thread(
            target=agent_loop, args=(args.url, tok, args, stats, stop, i), daemon=True
        )
        for i, tok in enumerate(tokens)
    ]
    print(
        f"{len(tokens)} agent, {args.duration:.0f} s, interval {args.interval} s, naqsh {args.pattern}"
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = sum(stats.codes.values()) + stats.errors
    ok = stats.codes.get(200, 0)
    p50, p95, p99 = (pct(stats.lat_ms, q) for q in (0.5, 0.95, 0.99))
    print(
        f"so'rovlar: {total}, 200: {ok}, kodlar: {stats.codes}, tarmoq xatosi: {stats.errors}"
    )
    if stats.lat_ms:
        print(
            f"kechikish ms: p50={p50:.0f} p95={p95:.0f} p99={p99:.0f} "
            f"o'rtacha={statistics.fmean(stats.lat_ms):.0f} maks={max(stats.lat_ms):.0f}"
        )
    failures = []
    if total == 0 or ok != total:
        failures.append(
            f"xato ulushi {100 * (total - ok) / max(total, 1):.1f}% (kutilgan 0%)"
        )
    if p95 > args.p95_ms:
        failures.append(f"p95 {p95:.0f} ms > {args.p95_ms:.0f} ms")
    if p99 > args.p99_ms:
        failures.append(f"p99 {p99:.0f} ms > {args.p99_ms:.0f} ms")
    if failures:
        print("MEZON BUZILDI: " + "; ".join(failures))
        return 1
    print("MEZONLAR BAJARILDI (T-P-01/02)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
