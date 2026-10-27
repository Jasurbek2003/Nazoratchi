/** Yagona holat lug'ati (TZ 13.4.1) va aggregatsiya (13.4.2). */

export type Status = "ok" | "warning" | "high" | "critical" | "unknown" | "paused" | "info";

export const STATUS_META: Record<Status, { label: string; glyph: string }> = {
  ok: { label: "Joyida", glyph: "✓" },
  warning: { label: "Diqqat", glyph: "▲" },
  high: { label: "Muhim", glyph: "▲▲" },
  critical: { label: "Kritik", glyph: "✖" },
  unknown: { label: "Noma'lum", glyph: "?" },
  paused: { label: "Pauza", glyph: "⏸" },
  info: { label: "Ma'lumot", glyph: "i" },
};

/** Og'irlik tartibi: critical > high > warning > unknown > ok. */
const RANK: Record<Status, number> = { critical: 5, high: 4, warning: 3, unknown: 2, info: 1, paused: 0, ok: 0 };

export function statusRank(s: Status): number {
  return RANK[s];
}

/** Eng yomoni. `unknown` faqat qolganlar `ok` bo'lsa ko'rinadi (RANK shuni ta'minlaydi). Bo'sh ro'yxat -> unknown. */
export function worstStatus(list: readonly Status[]): Status {
  if (list.length === 0) return "unknown";
  let worst: Status = "ok";
  for (const s of list) if (RANK[s] > RANK[worst]) worst = s;
  return worst;
}

export type Severity = "info" | "warning" | "high" | "critical";
export const SEVERITY_ORDER: readonly Severity[] = ["info", "warning", "high", "critical"];

export function severityStatus(severity: string): Status {
  return (SEVERITY_ORDER as readonly string[]).includes(severity) ? (severity as Status) : "unknown";
}

export function severityRank(severity: string): number {
  return SEVERITY_ORDER.indexOf(severity as Severity);
}

/** Sertifikat muddati chegaralari 21/7/3 (TZ 13.6 CertBadge). */
export function certStatus(daysLeft: number | null | undefined): Status {
  if (daysLeft == null) return "unknown";
  if (daysLeft <= 3) return "critical";
  if (daysLeft <= 7) return "high";
  if (daysLeft <= 21) return "warning";
  return "ok";
}

/** Foizli resurs (CPU/RAM/disk) uchun rang chegarasi. */
export function usageStatus(percent: number | null | undefined): Status {
  if (percent == null || !Number.isFinite(percent)) return "unknown";
  if (percent >= 95) return "critical";
  if (percent >= 85) return "warning";
  return "ok";
}

export function probeStatus(state: string): Status {
  switch (state) {
    case "up":
      return "ok";
    case "down":
      return "critical";
    case "paused":
      return "paused";
    default:
      return "unknown";
  }
}

export const PROBE_STATE_LABEL: Record<string, string> = {
  up: "Ishlayapti",
  down: "Ishlamayapti",
  unknown: "Noma'lum",
  paused: "To'xtatilgan",
};

export const SERVER_STATUS_LABEL: Record<string, string> = {
  new: "Yangi",
  online: "Onlayn",
  offline: "Aloqada emas",
  paused: "Pauza",
  archived: "Arxiv",
};
