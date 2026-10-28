import { z } from "zod";
import type { MaintenanceWindow, Matcher } from "../api/types";

export const MIN_SILENCE_MIN = 15;
export const MAX_SILENCE_DAYS = 30;

export const MATCHER_LABELS: { value: string; label: string }[] = [
  { value: "server", label: "Server" },
  { value: "project", label: "Loyiha" },
  { value: "rule", label: "Qoida" },
  { value: "severity", label: "Ahamiyat" },
  { value: "tag", label: "Teg" },
  { value: "domain", label: "Domen" },
  { value: "container", label: "Konteyner" },
];

export const MATCHER_OPS: { value: Matcher["op"]; label: string }[] = [
  { value: "=", label: "teng (=)" },
  { value: "!=", label: "teng emas (!=)" },
  { value: "=~", label: "regex (=~)" },
];

export const DURATIONS: { value: string; label: string; minutes: number }[] = [
  { value: "1h", label: "1 soat", minutes: 60 },
  { value: "4h", label: "4 soat", minutes: 240 },
  { value: "24h", label: "24 soat", minutes: 1440 },
  { value: "7d", label: "7 kun", minutes: 7 * 1440 },
  { value: "custom", label: "Maxsus", minutes: 0 },
];

/** `datetime-local` qiymati (brauzer mahalliy vaqti) -> Date; noto'g'ri bo'lsa null. */
export function parseLocal(value: string): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Date -> `datetime-local` qiymati ("2026-10-28T14:30"), mahalliy vaqtda. */
export function toLocalInput(date: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
}

const matcherSchema = z.object({
  label: z.string().min(1, "Moslash maydonini tanlang."),
  op: z.enum(["=", "!=", "=~"]),
  value: z.string().trim().min(1, "Qiymatni kiriting.").max(200, "Qiymat 200 belgidan oshmasin."),
});

export const silenceSchema = z
  .object({
    matchers: z.array(matcherSchema).min(1, "Kamida bitta shart kerak.").max(10, "Ko'pi bilan 10 ta shart."),
    duration: z.enum(["1h", "4h", "24h", "7d", "custom"]),
    custom_ends: z.string(),
    reason: z.string().trim().min(1, "Sababni yozing."),
  })
  .superRefine((v, ctx) => {
    if (v.duration !== "custom") return;
    const end = parseLocal(v.custom_ends);
    const mins = end ? (end.getTime() - Date.now()) / 60_000 : NaN;
    if (!end) ctx.addIssue({ code: "custom", path: ["custom_ends"], message: "Tugash vaqtini kiriting." });
    else if (mins < MIN_SILENCE_MIN) ctx.addIssue({ code: "custom", path: ["custom_ends"], message: "Muddat kamida 15 daqiqa bo'lishi kerak." });
    else if (mins > MAX_SILENCE_DAYS * 1440) ctx.addIssue({ code: "custom", path: ["custom_ends"], message: "Muddat 30 kundan oshmasin." });
  });
export type SilenceForm = z.infer<typeof silenceSchema>;

export function silenceEndsAt(v: SilenceForm): string {
  if (v.duration === "custom") return parseLocal(v.custom_ends)!.toISOString();
  const minutes = DURATIONS.find((d) => d.value === v.duration)!.minutes;
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

export const maintenanceSchema = z
  .object({
    servers: z.array(z.string()),
    projects: z.array(z.string()),
    starts_at: z.string().min(1, "Boshlanish vaqtini kiriting."),
    ends_at: z.string().min(1, "Tugash vaqtini kiriting."),
    reason: z.string().trim().min(1, "Sababni yozing."),
  })
  .superRefine((v, ctx) => {
    if (v.servers.length + v.projects.length === 0) {
      ctx.addIssue({ code: "custom", path: ["servers"], message: "Kamida bitta server yoki loyihani tanlang." });
    }
    const s = parseLocal(v.starts_at);
    const e = parseLocal(v.ends_at);
    if (s && e) {
      if (e <= s) ctx.addIssue({ code: "custom", path: ["ends_at"], message: "Tugash vaqti boshlanishdan keyin bo'lishi kerak." });
      else if (e.getTime() - s.getTime() > MAX_SILENCE_DAYS * 86_400_000) ctx.addIssue({ code: "custom", path: ["ends_at"], message: "Oyna 30 kundan uzun bo'lmasin." });
    }
  });
export type MaintenanceForm = z.infer<typeof maintenanceSchema>;

export function describeMatcher(m: Matcher): string {
  const label = MATCHER_LABELS.find((l) => l.value === m.label)?.label ?? m.label;
  return `${label} ${m.op} ${m.value}`;
}

/** Texnik ish oynasi holati: rejalashtirilgan / davom etmoqda. */
export function windowPhase(w: Pick<MaintenanceWindow, "starts_at" | "ends_at">, now: number): "scheduled" | "active" {
  return Date.parse(w.starts_at) > now ? "scheduled" : "active";
}
