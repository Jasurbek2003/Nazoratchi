import { useFilesystems } from "../../api/queries";
import type { Filesystem } from "../../api/types";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/Feedback";
import { GaugeBar, StaleChip } from "../../components/Indicators";
import { StatusBadge } from "../../components/Status";
import { formatBytes, formatNumber } from "../../lib/format";
import { isStale } from "../../lib/freshness";
import type { Status } from "../../lib/status";
import { useNow } from "../../lib/useNow";

/** To'lishga qolgan kun bo'yicha holat (bashorat yo'q bo'lsa — null). */
export function forecastStatus(days: number | null | undefined): Status | null {
  if (days == null) return null;
  if (days <= 3) return "critical";
  if (days <= 7) return "high";
  if (days <= 14) return "warning";
  return "ok";
}

export function FilesystemsTab({ serverId }: { serverId: string }) {
  const q = useFilesystems(serverId);
  const now = useNow();
  if (q.isPending) return <SkeletonRows rows={3} className="h-14" />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Fayl tizimlarini yuklab bo'lmadi" />;
  const items: Filesystem[] = q.data ?? [];
  if (items.length === 0) return <EmptyState title="Fayl tizimi ma'lumoti yo'q" hint="Agent diskni o'lchagach, bandlik shu yerda ko'rinadi." />;
  return (
    <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2">
      {items.map((fs) => {
        const stale = isStale(fs.time, now);
        const f = forecastStatus(fs.days_until_full);
        return (
          <li key={fs.mount} className={`panel p-4 ${stale ? "opacity-80" : ""}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="mono truncate text-[15px] font-semibold" title={fs.mount}>
                  {fs.mount}
                </p>
                <p className="text-xs text-muted">
                  {fs.device} · {fs.fstype}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {fs.readonly && <StatusBadge status="critical" label="Faqat o'qish" size="sm" />}
                {stale && <StaleChip />}
              </div>
            </div>
            <div className="mt-3">
              <GaugeBar label="Band" value={fs.used_percent} stale={stale} />
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-[13px]">
              <div>
                <dt className="text-muted">Band</dt>
                <dd className="num font-medium">{formatBytes(fs.used_bytes)}</dd>
              </div>
              <div>
                <dt className="text-muted">Bo&apos;sh</dt>
                <dd className="num font-medium">{formatBytes(fs.avail_bytes)}</dd>
              </div>
              <div>
                <dt className="text-muted">Jami</dt>
                <dd className="num font-medium">{formatBytes(fs.total_bytes)}</dd>
              </div>
            </dl>
            <div className="mt-3 border-t border-line pt-2 text-[13px]">
              {stale ? (
                <span className="text-muted">Bashorat eskirgan ma&apos;lumotga asoslanadi.</span>
              ) : f ? (
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={f} size="sm" label={`${formatNumber(fs.days_until_full, 1)} kunda to'ladi`} />
                </span>
              ) : (
                <span className="text-muted">To&apos;lishga qolgan vaqt: bashorat yo&apos;q (o&apos;sish aniqlanmadi)</span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
