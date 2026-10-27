/**
 * Grafik ma'lumotini tayyorlash (uPlot `AlignedData`). API nuqtalari `[ms, qiymat | null]`;
 * `null` — ma'lumot yo'q: chiziq UZILADI (uPlot `spanGaps: false`), tutashtirilmaydi (TZ 13.4.4).
 */
import type { RawPoint } from "../api/types";

export interface Aligned {
  /** Epoch soniya (uPlot vaqt o'qi). */
  xs: number[];
  ys: (number | null)[][];
}

export function toAligned(seriesPoints: RawPoint[][]): Aligned {
  const stamps = new Set<number>();
  for (const pts of seriesPoints) for (const [t] of pts) stamps.add(t);
  const sorted = [...stamps].sort((a, b) => a - b);
  const ys = seriesPoints.map((pts) => {
    const byTime = new Map<number, number | null>();
    for (const [t, v] of pts) byTime.set(t, v == null || !Number.isFinite(v) ? null : v);
    return sorted.map((t) => byTime.get(t) ?? null);
  });
  return { xs: sorted.map((t) => t / 1000), ys };
}

/** Bir necha seriyani (masalan, tarmoq interfeyslari) vaqt bo'yicha yig'ib bitta qiladi. Hammasi null bo'lsa — null. */
export function sumSeries(seriesPoints: RawPoint[][]): RawPoint[] {
  const { xs, ys } = toAligned(seriesPoints);
  return xs.map((x, i) => {
    let total: number | null = null;
    for (const col of ys) {
      const v = col[i];
      if (v != null) total = (total ?? 0) + v;
    }
    return [x * 1000, total] as RawPoint;
  });
}

/** Barcha seriyalarda ma'lumot yo'q oraliqlar: [boshlanish x, tugash x] (qo'shni haqiqiy nuqtalargacha). */
export function nullRuns(xs: number[], ys: (number | null)[][]): [number, number][] {
  const runs: [number, number][] = [];
  if (xs.length === 0) return runs;
  const empty = (i: number) => ys.every((col) => col[i] == null);
  let i = 0;
  while (i < xs.length) {
    if (!empty(i)) {
      i += 1;
      continue;
    }
    let j = i;
    while (j + 1 < xs.length && empty(j + 1)) j += 1;
    const start = i > 0 ? xs[i - 1]! : xs[i]!;
    const end = j + 1 < xs.length ? xs[j + 1]! : xs[j]!;
    runs.push([start, end]);
    i = j + 1;
  }
  return runs;
}

/** "Ma'lumotlar jadvali" (ekran o'quvchi uchun) — ko'pi bilan `max` qator, teng oraliqda. */
export function tableRows(xs: number[], ys: (number | null)[][], max = 40): { x: number; values: (number | null)[] }[] {
  if (xs.length === 0) return [];
  const step = Math.max(1, Math.ceil(xs.length / max));
  const rows: { x: number; values: (number | null)[] }[] = [];
  for (let i = xs.length - 1; i >= 0; i -= step) rows.push({ x: xs[i]!, values: ys.map((col) => col[i] ?? null) });
  return rows;
}

/** Sparkline uchun: oxirgi `max` ta nuqta, null saqlanadi. */
export function sparkValues(points: RawPoint[] | undefined, max = 60): (number | null)[] {
  if (!points) return [];
  const vals = points.map((p) => p[1]);
  return vals.length > max ? vals.slice(vals.length - max) : vals;
}
