import type { BackupState } from "../api/types";
import type { Status } from "./status";

/** Zaxira holati -> umumiy holat lug'ati (TZ 13.4.1). `problem` — "Faqat muammolilar" filtri uchun. */
export const BACKUP_STATE: Record<BackupState, { status: Status; label: string; problem: boolean }> = {
  ok: { status: "ok", label: "Joyida", problem: false },
  late: { status: "warning", label: "Kechikdi", problem: true },
  critical: { status: "critical", label: "Juda kechikdi", problem: true },
  failed: { status: "critical", label: "Xato bilan tugadi", problem: true },
  stale: { status: "unknown", label: "Agent jim", problem: true },
  missing: { status: "critical", label: "Zaxira yo'q", problem: true },
  unknown: { status: "unknown", label: "Noma'lum", problem: false },
  none: { status: "unknown", label: "Kutilmaydi", problem: false },
};

export function backupState(state: string): (typeof BACKUP_STATE)[BackupState] {
  return BACKUP_STATE[state as BackupState] ?? BACKUP_STATE.unknown;
}

/** Soatlarni "6 soat" / "2 kun 3 soat" ko'rinishida (null -> tire). */
export function formatHours(hours: number | null | undefined): string {
  if (hours == null || !Number.isFinite(hours) || hours < 0) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} daqiqa`;
  if (hours < 48) return `${Math.round(hours)} soat`;
  return `${Math.floor(hours / 24)} kun`;
}

/** DNS javobi (massiv yoki matn) -> matn ro'yxati. */
export function answerList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
  if (typeof value === "string" && value) return [value];
  return [];
}
