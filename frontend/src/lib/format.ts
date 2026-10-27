/** Formatlash (TZ 13.10): faqat Intl; vaqt zonasi — foydalanuvchi zonasi (standart Asia/Tashkent). */

export const DEFAULT_TZ = "Asia/Tashkent";
const NUM_LOCALE = "uz";
const EM = "—";

export function safeTimeZone(tz: string | undefined | null): string {
  if (!tz) return DEFAULT_TZ;
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
    return tz;
  } catch {
    return DEFAULT_TZ;
  }
}

export function formatNumber(value: number | null | undefined, maxFractionDigits = 1): string {
  if (value == null || !Number.isFinite(value)) return EM;
  return new Intl.NumberFormat(NUM_LOCALE, { maximumFractionDigits: maxFractionDigits }).format(value);
}

/** Foiz yopishiq: "78%" (TZ 13.15). */
export function formatPercent(value: number | null | undefined, maxFractionDigits = 0): string {
  if (value == null || !Number.isFinite(value)) return EM;
  return `${formatNumber(value, maxFractionDigits)}%`;
}

const BYTE_UNITS = ["bayt", "KB", "MB", "GB", "TB", "PB"] as const;

/** 1024 asosida: "46 MB". */
export function formatBytes(bytes: number | null | undefined, maxFractionDigits = 1): string {
  if (bytes == null || !Number.isFinite(bytes)) return EM;
  let value = Math.abs(bytes);
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : maxFractionDigits;
  const sign = bytes < 0 ? "-" : "";
  return `${sign}${formatNumber(value, digits)} ${BYTE_UNITS[unit]}`;
}

export function formatRate(bytesPerSec: number | null | undefined): string {
  if (bytesPerSec == null || !Number.isFinite(bytesPerSec)) return EM;
  return `${formatBytes(bytesPerSec)}/s`;
}

/** Davomiylik: "4 kun 3 soat", "12 daqiqa", "35 soniya". Ikki eng katta birlik. */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds) || totalSeconds < 0) return EM;
  const s = Math.floor(totalSeconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return h > 0 ? `${d} kun ${h} soat` : `${d} kun`;
  if (h > 0) return m > 0 ? `${h} soat ${m} daqiqa` : `${h} soat`;
  if (m > 0) return `${m} daqiqa`;
  return `${s} soniya`;
}

/** Nisbiy vaqt: "3 soniya oldin". 5 soniyadan kam — "hozir". */
export function formatAgo(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return EM;
  const s = Math.max(0, Math.floor(seconds));
  if (s < 5) return "hozir";
  if (s < 60) return `${s} soniya oldin`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} daqiqa oldin`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} soat oldin`;
  return `${Math.floor(h / 24)} kun oldin`;
}

export function ageSeconds(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : (now - t) / 1000;
}

export function formatAgoFrom(iso: string | null | undefined, now: number): string {
  const age = ageSeconds(iso, now);
  return age == null ? "hech qachon" : formatAgo(age);
}

/** Mutlaq vaqt: "2026-10-22 14:35" foydalanuvchi zonasida. */
export function formatDateTime(iso: string | number | null | undefined, tz?: string | null): string {
  if (iso == null || iso === "") return EM;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EM;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: safeTimeZone(tz),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
}

const MONTHS_UZ = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];

/** Grafik o'qi uchun: kichik oraliqda "09:30", uzun oraliqda "22 okt". */
export function formatAxisTime(epochSeconds: number, tz: string | null | undefined, withDate: boolean): string {
  const date = new Date(epochSeconds * 1000);
  const zone = safeTimeZone(tz);
  if (withDate) {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone, month: "numeric", day: "numeric" }).formatToParts(date);
    const month = Number(parts.find((p) => p.type === "month")?.value ?? 1);
    const day = parts.find((p) => p.type === "day")?.value ?? "";
    return `${day} ${MONTHS_UZ[month - 1] ?? ""}`;
  }
  return new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}

export function formatDaysLeft(days: number | null | undefined): string {
  if (days == null || !Number.isFinite(days)) return EM;
  if (days < 0) return `${Math.abs(Math.trunc(days))} kun oldin tugagan`;
  return `${formatNumber(days, 0)} kun`;
}
