import type { Probe, Project } from "../api/types";
import { isStale } from "./freshness";
import { probeStatus, worstStatus, type Status } from "./status";

export const KIND_LABEL: Record<Project["kind"], string> = {
  compose: "Docker Compose",
  systemd: "systemd",
  static: "Statik sayt",
  other: "Boshqa",
};

/** Tekshiruv eskirganmi: oxirgi ishga tushirish 3 interval + 30 s dan oldin (yoki hech bo'lmagan). */
export function probeStale(p: Pick<Probe, "enabled" | "last_run_at" | "interval_s">, now: number): boolean {
  if (!p.enabled) return false;
  return isStale(p.last_run_at, now, p.interval_s * 3 + 30);
}

/** Probe holati: yoqilmagan -> pauza; eskirgan -> noma'lum (eski "up" hozirgi deb ko'rsatilmaydi). */
export function effectiveProbeStatus(p: Probe, now: number): Status {
  if (!p.enabled) return "paused";
  if (probeStale(p, now)) return "unknown";
  return probeStatus(p.state);
}

export interface ProjectHealth {
  status: Status;
  label: string;
  /** Muammoli tekshiruvlar soni */
  failing: number;
  total: number;
}

export function projectHealth(project: Project, probes: Probe[], now: number): ProjectHealth {
  if (project.status === "archived") return { status: "paused", label: "Arxiv", failing: 0, total: 0 };
  const mine = probes.filter((p) => p.project === project.id && p.enabled);
  if (mine.length === 0) return { status: "unknown", label: "Tekshiruv yo'q", failing: 0, total: 0 };
  const states = mine.map((p) => effectiveProbeStatus(p, now));
  const status = worstStatus(states);
  const failing = states.filter((s) => s === "critical").length;
  const label = status === "ok" ? "Joyida" : status === "critical" ? `${failing} ta tekshiruv ishlamayapti` : "Noma'lum";
  return { status, label, failing, total: mine.length };
}
