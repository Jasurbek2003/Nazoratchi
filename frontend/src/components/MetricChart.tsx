import uPlot from "uplot";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { RawPoint } from "../api/types";
import { nullRuns, tableRows, toAligned } from "../lib/chart";
import { formatDateTime, formatNumber, formatPercent, formatRate, safeTimeZone } from "../lib/format";
import { useResolvedTheme } from "../lib/theme";
import { ErrorState, Skeleton } from "./Feedback";

export type ChartUnit = "percent" | "rate" | "number";

export interface ChartSeries {
  label: string;
  /** CSS o'zgaruvchi nomi, masalan `--series-1` (mavzuga moslashadi). */
  colorVar: string;
  points: RawPoint[];
}

const SYNC_KEY = "nzr-sync";

export function formatByUnit(unit: ChartUnit, v: number | null | undefined): string {
  if (v == null) return "—";
  if (unit === "percent") return formatPercent(v, 1);
  if (unit === "rate") return formatRate(v);
  return formatNumber(v, 2);
}

/** `light-dark()` ni hal qilingan rangga aylantiradi (canvas CSS o'zgaruvchini tushunmaydi). */
function resolveColor(varName: string): string {
  const probe = document.createElement("span");
  probe.style.color = `var(${varName})`;
  probe.style.display = "none";
  document.body.appendChild(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();
  return color || "#888";
}

interface Props {
  title: string;
  unit: ChartUnit;
  series: ChartSeries[];
  tz?: string | null;
  height?: number;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Eskirgan bo'lsa sarlavha yonida ko'rsatiladigan izoh. */
  note?: string;
}

/** uPlot o'rami: `null` nuqta — ko'rinadigan bo'shliq, chiziq tutashtirilmaydi; kursor sinxron; jadval ko'rinishi. */
export const MetricChart = memo(function MetricChart({ title, unit, series, tz, height = 190, loading, error, onRetry, note }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const fullRangeRef = useRef<[number, number] | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const theme = useResolvedTheme();
  const zone = safeTimeZone(tz);

  const aligned = useMemo(() => toAligned(series.map((s) => s.points)), [series]);
  const hasData = aligned.ys.some((col) => col.some((v) => v != null));
  const structureKey = series.map((s) => `${s.label}|${s.colorVar}`).join(",");

  const alignedRef = useRef(aligned);
  alignedRef.current = aligned;

  // uPlot nusxasi: tuzilma, mavzu, zona, birlik o'zgarganda qayta quriladi.
  useEffect(() => {
    const host = hostRef.current;
    if (!host || !hasData) return;
    const colors = series.map((s) => resolveColor(s.colorVar));
    const grid = resolveColor("--chart-grid");
    const gap = resolveColor("--chart-gap");
    const text = resolveColor("--muted");
    const axisFont = "12px " + (getComputedStyle(document.body).fontFamily || "sans-serif");
    const fmtAxis = (_u: uPlot, splits: number[]) => splits.map((v) => formatByUnit(unit, v).replace(/\.0%$/, "%"));

    const opts: uPlot.Options = {
      width: Math.max(host.clientWidth, 240),
      height,
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1000), zone),
      cursor: { sync: { key: SYNC_KEY }, drag: { x: true, y: false, setScale: true } },
      scales: {
        x: { time: true },
        y: {
          range: (_u, min, max) => (unit === "percent" ? [0, 100] : [0, Math.max(max * 1.15, min + 1, 1)]),
        },
      },
      axes: [
        { stroke: text, font: axisFont, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid } },
        { stroke: text, font: axisFont, size: unit === "rate" ? 78 : 56, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid }, values: fmtAxis },
      ],
      series: [
        { label: "Vaqt", value: (_u, v) => (v == null ? "" : formatDateTime(v * 1000, zone)) },
        ...series.map((s, i) => ({
          label: s.label,
          stroke: colors[i]!,
          width: 1.75,
          spanGaps: false,
          points: { show: false },
          value: (_u: uPlot, v: number | null) => formatByUnit(unit, v),
        })),
      ],
      legend: { live: true },
      hooks: {
        // "Ma'lumot yo'q" oraliqlari: kulrang fon (TZ 13.4.4), chiziq tutashtirilmaydi.
        drawClear: [
          (u) => {
            const { xs, ys } = alignedRef.current;
            const runs = nullRuns(xs, ys);
            if (runs.length === 0) return;
            const { ctx, bbox } = u;
            ctx.save();
            ctx.fillStyle = gap;
            for (const [a, b] of runs) {
              const x1 = u.valToPos(a, "x", true);
              const x2 = u.valToPos(b, "x", true);
              ctx.fillRect(Math.max(bbox.left, x1), bbox.top, Math.max(2, Math.min(bbox.left + bbox.width, x2) - Math.max(bbox.left, x1)), bbox.height);
            }
            ctx.restore();
          },
        ],
        setScale: [
          (u, key) => {
            if (key !== "x") return;
            const full = fullRangeRef.current;
            const min = u.scales.x?.min;
            const max = u.scales.x?.max;
            setZoomed(!!full && min != null && max != null && (Math.abs(min - full[0]) > 1 || Math.abs(max - full[1]) > 1));
          },
        ],
      },
    };

    const { xs, ys } = alignedRef.current;
    fullRangeRef.current = xs.length ? [xs[0]!, xs[xs.length - 1]!] : null;
    const plot = new uPlot(opts, [xs, ...ys] as uPlot.AlignedData, host);
    plotRef.current = plot;
    setZoomed(false);

    const ro = new ResizeObserver(() => plot.setSize({ width: Math.max(host.clientWidth, 240), height }));
    ro.observe(host);
    return () => {
      ro.disconnect();
      plot.destroy();
      plotRef.current = null;
    };
    // `series` ro'yxati ataylab chiqarilgan: ma'lumot alohida effektda yangilanadi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey, unit, theme, zone, height, hasData]);

  // Ma'lumot yangilanganda butun grafik qayta chizilmaydi (TZ 13.7).
  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    fullRangeRef.current = aligned.xs.length ? [aligned.xs[0]!, aligned.xs[aligned.xs.length - 1]!] : null;
    plot.setData([aligned.xs, ...aligned.ys] as uPlot.AlignedData);
  }, [aligned]);

  const resetZoom = () => {
    const plot = plotRef.current;
    const full = fullRangeRef.current;
    if (plot && full) plot.setScale("x", { min: full[0], max: full[1] });
  };

  const rows = useMemo(() => (hasData ? tableRows(aligned.xs, aligned.ys, 30) : []), [aligned, hasData]);

  return (
    <figure className="panel m-0 min-w-0 p-3" aria-label={title}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <figcaption className="font-semibold">
          {title}
          {note && <span className="ml-2 text-xs font-normal text-warning-fg">{note}</span>}
        </figcaption>
        {zoomed && (
          <button type="button" className="btn !min-h-7 px-2 text-xs" onClick={resetZoom}>
            Qaytarish
          </button>
        )}
      </div>
      {error ? (
        <ErrorState error={error} onRetry={onRetry} title="Grafikni yuklab bo'lmadi" />
      ) : loading && !hasData ? (
        <Skeleton className="w-full" label="Grafik yuklanmoqda" />
      ) : !hasData ? (
        <div className="flex items-center justify-center rounded text-muted" style={{ height }}>
          <p>Bu oraliqda ma&apos;lumot yo&apos;q</p>
        </div>
      ) : (
        <div ref={hostRef} className="w-full min-w-0 overflow-hidden" style={{ minHeight: height }} aria-hidden="true" />
      )}
      {loading && !error && hasData && <p className="sr-only" role="status">Grafik yangilanmoqda</p>}
      {hasData && (
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer select-none">Ma&apos;lumotlar jadvali</summary>
          <div className="mt-2 max-h-56 overflow-auto">
            <table className="w-full border-collapse text-left num">
              <thead>
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">Vaqt</th>
                  {series.map((s) => (
                    <th key={s.label} scope="col" className="py-1 pr-3 font-medium">{s.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.x} className="border-t border-line">
                    <td className="py-0.5 pr-3">{formatDateTime(r.x * 1000, zone)}</td>
                    {r.values.map((v, i) => (
                      <td key={i} className="py-0.5 pr-3">{v == null ? "ma'lumot yo'q" : formatByUnit(unit, v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
});
