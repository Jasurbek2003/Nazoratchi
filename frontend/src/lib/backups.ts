import { z } from "zod";
import type { BackupState, DrillResult, DrillSummary } from "../api/types";
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

export const DRILL_RESULT: Record<DrillResult, { status: Status; label: string }> = {
  success: { status: "ok", label: "Muvaffaqiyatli" },
  partial: { status: "warning", label: "Qisman" },
  failed: { status: "critical", label: "Muvaffaqiyatsiz" },
};

/** Zaxira ro'yxati/kartasidagi drill belgisi (R-117: "hech qachon" va muddati o'tgan ko'rinsin). */
export function drillBadge(d: DrillSummary): { status: Status; label: string } {
  if (d.never) return { status: "warning", label: d.last ? "Drill muvaffaqiyatsiz" : "Drill: hech qachon" };
  if (d.overdue) return { status: "warning", label: `Drill muddati o'tgan (${d.last_success_days} kun)` };
  return { status: "ok", label: `Drill: ${d.last_success_days} kun oldin` };
}

/** Soniyalar -> "14 daq 20 s" (RTO bahosi). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h) return `${h} soat ${m} daq`;
  if (m) return s ? `${m} daq ${s} s` : `${m} daq`;
  return `${s} s`;
}

const optionalInt = (label: string) =>
  z.string().trim().refine((v) => v === "" || /^\d+$/.test(v), `${label} butun, manfiy bo'lmagan son bo'lsin.`);

export const drillSchema = z.object({
  performed_at: z
    .string()
    .min(1, "Sanani kiriting.")
    .refine((v) => new Date(v).getTime() <= Date.now() + 5 * 60_000, "Kelajak sanasini kiritib bo'lmaydi."),
  backup_file: z.string().trim().min(1, "Zaxira fayli nomini kiriting.").max(300, "Nom 300 belgidan oshmasin."),
  result: z.enum(["success", "partial", "failed"]),
  backup_age_h: optionalInt("Zaxira yoshi"),
  duration_s: optionalInt("Davomiylik"),
  tables_count: optionalInt("Jadvallar soni"),
  rows_count: optionalInt("Qatorlar soni"),
  notes: z.string().max(2000, "Izoh 2000 belgidan oshmasin."),
});
export type DrillForm = z.infer<typeof drillSchema>;

/** Forma qiymati -> API tanasi (bo'sh maydonlar `null`). */
export function drillBody(project: string, v: DrillForm) {
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  return {
    project,
    performed_at: new Date(v.performed_at).toISOString(),
    backup_file: v.backup_file.trim(),
    result: v.result,
    backup_age_h: num(v.backup_age_h),
    duration_s: num(v.duration_s),
    tables_count: num(v.tables_count),
    rows_count: num(v.rows_count),
    notes: v.notes,
  };
}

/** DNS javobi (massiv yoki matn) -> matn ro'yxati. */
export function answerList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
  if (typeof value === "string" && value) return [value];
  return [];
}
