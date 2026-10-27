import { useMemo } from "react";
import { useMetrics } from "../../api/queries";
import type { QueryResponse, RawPoint } from "../../api/types";
import { MetricChart, type ChartSeries, type ChartUnit } from "../../components/MetricChart";
import { sumSeries } from "../../lib/chart";
import { STALE_AFTER_S } from "../../lib/freshness";
import { useNow } from "../../lib/useNow";

interface MetricSpec {
  name: string;
  /** `sum` — barcha seriyalar (interfeyslar) yig'indisi; `each` — har seriya alohida (label bo'yicha). */
  mode: "sum" | "each";
  label: string;
  labelKey?: string;
  colorVar?: string;
}

interface ChartSpec {
  id: string;
  title: string;
  unit: ChartUnit;
  metrics: MetricSpec[];
}

const CHARTS: ChartSpec[] = [
  { id: "cpu", title: "CPU band (%)", unit: "percent", metrics: [{ name: "cpu_busy_percent", mode: "sum", label: "CPU", colorVar: "--series-1" }] },
  { id: "mem", title: "RAM band (%)", unit: "percent", metrics: [{ name: "mem_used_percent", mode: "sum", label: "RAM", colorVar: "--series-1" }] },
  {
    id: "load",
    title: "Yuklama (load average)",
    unit: "number",
    metrics: [
      { name: "load1", mode: "sum", label: "1 daqiqa", colorVar: "--series-1" },
      { name: "load5", mode: "sum", label: "5 daqiqa", colorVar: "--series-2" },
      { name: "load15", mode: "sum", label: "15 daqiqa", colorVar: "--series-3" },
    ],
  },
  { id: "disk", title: "Disk band (%)", unit: "percent", metrics: [{ name: "fs_used_percent", mode: "each", label: "Disk", labelKey: "mount" }] },
  {
    id: "net",
    title: "Tarmoq (bayt/s)",
    unit: "rate",
    metrics: [
      { name: "net_rx_bytes_per_sec", mode: "sum", label: "Kiruvchi", colorVar: "--series-1" },
      { name: "net_tx_bytes_per_sec", mode: "sum", label: "Chiquvchi", colorVar: "--series-2" },
    ],
  },
];

const SERIES_VARS = ["--series-1", "--series-2", "--series-3", "--series-4"];
const MAX_SERIES = 4;

function pointsOf(res: QueryResponse | undefined, spec: MetricSpec): ChartSeries[] {
  if (!res) return [];
  if (spec.mode === "sum") {
    return [{ label: spec.label, colorVar: spec.colorVar ?? SERIES_VARS[0]!, points: sumSeries(res.series.map((s) => s.points)) }];
  }
  return res.series.slice(0, MAX_SERIES).map((s, i) => ({
    label: (spec.labelKey && s.labels[spec.labelKey]) || spec.label,
    colorVar: SERIES_VARS[i % SERIES_VARS.length]!,
    points: s.points,
  }));
}

/** Oxirgi haqiqiy (null emas) nuqta vaqti — grafik eskirganini aniqlash uchun. */
export function lastRealTime(series: { points: RawPoint[] }[]): number | null {
  let last: number | null = null;
  for (const s of series) for (const [t, v] of s.points) if (v != null && (last == null || t > last)) last = t;
  return last;
}

function ServerChart({ spec, serverId, range, tz }: { spec: ChartSpec; serverId: string; range: string; tz?: string | null }) {
  const now = useNow();
  const results = useMetrics(
    serverId,
    spec.metrics.map((m) => m.name),
    range,
  );
  const dataKey = results.map((r) => r.dataUpdatedAt).join("|");
  const series = useMemo(
    () => results.flatMap((r, i) => pointsOf(r.data, spec.metrics[i]!)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dataKey, spec],
  );
  const error = results.find((r) => r.error && !r.data)?.error;
  const loading = results.some((r) => r.isPending || (r.isFetching && !r.data));
  const last = lastRealTime(series);
  const stale = last != null && (now - last) / 1000 > Math.max(STALE_AFTER_S, 120);
  return (
    <MetricChart
      title={spec.title}
      unit={spec.unit}
      series={series}
      tz={tz}
      loading={loading}
      error={error}
      onRetry={() => results.forEach((r) => void r.refetch())}
      note={stale ? "oxirgi ma'lumot eskirgan" : undefined}
    />
  );
}

export function ResourcesTab({ serverId, range, tz }: { serverId: string; range: string; tz?: string | null }) {
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {CHARTS.map((c) => (
        <ServerChart key={c.id} spec={c} serverId={serverId} range={range} tz={tz} />
      ))}
    </div>
  );
}
