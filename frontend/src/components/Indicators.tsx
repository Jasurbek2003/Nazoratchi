import { memo } from "react";
import { ageSeconds, formatAgo, formatDateTime, formatDaysLeft, formatPercent } from "../lib/format";
import { STALE_AFTER_S } from "../lib/freshness";
import { certStatus, usageStatus, type Status } from "../lib/status";
import { StatusBadge, STATUS_CLASS, StatusIcon } from "./Status";

/** "3 soniya oldin"; chegaradan eski bo'lsa sariq "eskirgan" (TZ 13.6 FreshnessLabel). */
export const FreshnessLabel = memo(function FreshnessLabel({
  iso,
  now,
  thresholdS = STALE_AFTER_S,
  tz,
  prefix,
}: {
  iso: string | null | undefined;
  now: number;
  thresholdS?: number;
  tz?: string | null;
  prefix?: string;
}) {
  const age = ageSeconds(iso, now);
  const stale = age == null || age > thresholdS;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 num" title={iso ? formatDateTime(iso, tz) : undefined}>
      <span className={stale ? "text-warning-fg" : "text-muted"}>
        {prefix}
        {age == null ? "hech qachon" : formatAgo(age)}
      </span>
      {stale && <StaleChip />}
    </span>
  );
});

export function StaleChip({ text = "eskirgan" }: { text?: string }) {
  return (
    <span
      data-stale="true"
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-[2px] text-[11px] font-medium leading-none ${STATUS_CLASS.warning.chip}`}
    >
      <StatusIcon status="warning" size={11} />
      {text}
    </span>
  );
}

/** Qolgan kun bo'yicha sertifikat belgisi, chegaralar 21/7/3. */
export const CertBadge = memo(function CertBadge({ daysLeft }: { daysLeft: number | null | undefined }) {
  const status: Status = certStatus(daysLeft);
  return <StatusBadge status={status} size="sm" label={daysLeft == null ? "Noma'lum" : formatDaysLeft(daysLeft)} />;
});

/** Foizli ko'rsatkich: chiziq + raqam + (eskirgan bo'lsa) belgi. `stale` bo'lsa rang o'chiriladi. */
export const GaugeBar = memo(function GaugeBar({
  value,
  stale,
  label,
  compact,
}: {
  value: number | null | undefined;
  stale?: boolean;
  label: string;
  compact?: boolean;
}) {
  const status = stale ? "unknown" : usageStatus(value);
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="min-w-0" aria-label={`${label}: ${value == null ? "ma'lumot yo'q" : formatPercent(value)}${stale ? ", eskirgan" : ""}`} role="img">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-muted">{label}</span>
        <span className={`num font-semibold ${stale ? "text-muted line-through decoration-1" : ""}`}>{formatPercent(value)}</span>
      </div>
      <div className={`mt-1 overflow-hidden rounded-full bg-line ${compact ? "h-1.5" : "h-2"}`}>
        <div className={`h-full rounded-full ${STATUS_CLASS[status].bar} ${stale ? "opacity-40" : ""}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
});
