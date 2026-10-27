import { memo } from "react";

/** Nuqtalarni `null` bo'yicha bo'laklarga ajratadi (bo'shliqda chiziq uziladi). */
export function sparkSegments(values: (number | null)[], width: number, height: number, min = 0, max = 100, pad = 2): string[] {
  const n = values.length;
  if (n === 0) return [];
  const span = max - min || 1;
  const x = (i: number) => (n === 1 ? width / 2 : (i / (n - 1)) * width);
  const y = (v: number) => pad + (1 - (Math.min(max, Math.max(min, v)) - min) / span) * (height - pad * 2);
  const segs: string[] = [];
  let cur = "";
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) {
      if (cur) segs.push(cur);
      cur = "";
      return;
    }
    const pt = `${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
    cur += cur ? ` L${pt}` : `M${pt}`;
  });
  if (cur) segs.push(cur);
  return segs;
}

/** Yengil sparkline (tooltip yo'q). `stale` bo'lsa kulrang va shtrixli — "hozirgi" deb o'qilmaydi. */
export const Sparkline = memo(function Sparkline({
  values,
  width = 96,
  height = 28,
  min = 0,
  max = 100,
  stale = false,
  label = "CPU, oxirgi 1 soat",
}: {
  values: (number | null)[];
  width?: number;
  height?: number;
  min?: number;
  max?: number;
  stale?: boolean;
  label?: string;
}) {
  const segs = sparkSegments(values, width, height, min, max);
  const has = values.some((v) => v != null);
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={has ? `${label}${stale ? " (eskirgan)" : ""}` : `${label}: ma'lumot yo'q`}
      className="block shrink-0"
    >
      <line x1="0" x2={width} y1={height - 1} y2={height - 1} stroke="var(--chart-grid)" strokeWidth="1" />
      {segs.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke={stale ? "var(--unknown)" : "var(--series-1)"}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={stale ? "3 3" : undefined}
        />
      ))}
    </svg>
  );
});
