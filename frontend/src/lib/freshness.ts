/** "Eskirgan" mantig'i (TZ 13.1 №6, 13.6 FreshnessLabel): eski raqam hech qachon "hozirgi" deb ko'rsatilmaydi. */
import { ageSeconds } from "./format";

/** Metrika/aloqa shu soniyadan eski bo'lsa — eskirgan (agent oralig'i 15-30 s). */
export const STALE_AFTER_S = 60;

/** Vaqt yo'q yoki chegaradan eski bo'lsa true. */
export function isStale(iso: string | null | undefined, now: number, thresholdS = STALE_AFTER_S): boolean {
  const age = ageSeconds(iso, now);
  return age == null || age > thresholdS;
}

export type Freshness = "fresh" | "stale" | "never";

export function freshness(iso: string | null | undefined, now: number, thresholdS = STALE_AFTER_S): Freshness {
  const age = ageSeconds(iso, now);
  if (age == null) return "never";
  return age > thresholdS ? "stale" : "fresh";
}
