/** Server holati: reyestr holati + incidentlar + ma'lumot yangiligi (TZ 13.4.2). */
import type { Incident, LatestResponse, Server } from "../api/types";
import { isStale } from "./freshness";
import { hostOf } from "./summary";
import { severityStatus, worstStatus, type Status } from "./status";

export interface DisplayStatus {
  status: Status;
  /** Aloqa/ma'lumot eskirgan: qiymatlar "hozirgi" deb ko'rsatilmaydi. */
  stale: boolean;
  label: string;
}

export function serverDisplayStatus(server: Server, incidents: Incident[], now: number): DisplayStatus {
  switch (server.status) {
    case "paused":
      return { status: "paused", stale: false, label: "Pauza" };
    case "archived":
      return { status: "unknown", stale: true, label: "Arxiv" };
    case "new":
      return { status: "unknown", stale: true, label: "Birinchi ma'lumot kutilmoqda" };
    case "offline":
      return { status: "critical", stale: true, label: "Aloqada emas" };
    default: {
      const stale = isStale(server.last_seen_at, now);
      if (stale) return { status: "unknown", stale: true, label: "Ma'lumot eskirgan" };
      const mine = incidents.filter((i) => i.status !== "resolved" && !i.suppressed && hostOf(i) === server.id);
      const status = worstStatus(["ok", ...mine.map((i) => severityStatus(i.severity))]);
      return { status, stale: false, label: status === "ok" ? "Onlayn" : "Onlayn, muammo bor" };
    }
  }
}

export interface Reading {
  value: number;
  time: string;
  stale: boolean;
  /** Disk uchun: eng to'lgan mount. */
  detail?: string;
}

export interface Vitals {
  cpu?: Reading;
  mem?: Reading;
  disk?: Reading;
  load1?: Reading;
  rx?: Reading;
  tx?: Reading;
}

function latestTime(points: { time: string }[]): string {
  return points.reduce((acc, p) => (Date.parse(p.time) > Date.parse(acc) ? p.time : acc), points[0]?.time ?? "");
}

/** `metrics/latest` javobidan joriy ko'rsatkichlar. Disk — eng to'lgan mount; tarmoq — interfeyslar yig'indisi. */
export function extractVitals(latest: LatestResponse | undefined, now: number): Vitals {
  const out: Vitals = {};
  if (!latest) return out;
  const m = latest.metrics;
  const single = (name: string): Reading | undefined => {
    const pts = m[name];
    if (!pts || pts.length === 0) return undefined;
    const time = latestTime(pts);
    const top = pts.reduce((a, b) => (b.value > a.value ? b : a));
    return { value: top.value, time, stale: isStale(time, now) };
  };
  const sum = (name: string): Reading | undefined => {
    const pts = m[name];
    if (!pts || pts.length === 0) return undefined;
    const time = latestTime(pts);
    return { value: pts.reduce((s, p) => s + p.value, 0), time, stale: isStale(time, now) };
  };
  out.cpu = single("cpu_busy_percent");
  out.mem = single("mem_used_percent");
  out.load1 = single("load1");
  const fs = m["fs_used_percent"];
  if (fs && fs.length > 0) {
    const top = fs.reduce((a, b) => (b.value > a.value ? b : a));
    const time = latestTime(fs);
    out.disk = { value: top.value, time, stale: isStale(time, now), detail: top.labels["mount"] };
  }
  out.rx = sum("net_rx_bytes_per_sec");
  out.tx = sum("net_tx_bytes_per_sec");
  return out;
}
