import { useContainers } from "../../api/queries";
import type { Container } from "../../api/types";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/Feedback";
import { StaleChip } from "../../components/Indicators";
import { StatusBadge } from "../../components/Status";
import { formatAgoFrom, formatDuration, formatNumber } from "../../lib/format";
import type { Status } from "../../lib/status";
import { useNow } from "../../lib/useNow";

const HEALTH: Record<number, { status: Status; label: string } | null> = {
  0: null,
  1: { status: "ok", label: "Sog'lom" },
  2: { status: "critical", label: "Nosog'lom" },
  3: { status: "info", label: "Ishga tushmoqda" },
};

/** Konteyner holati: eskirgan bo'lsa "noma'lum" (eski qiymat hozirgi deb ko'rsatilmaydi). */
export function containerStatus(c: Container): { status: Status; label: string } {
  if (c.stale) return { status: "unknown", label: "Noma'lum" };
  if (c.running) return { status: "ok", label: "Ishlayapti" };
  return c.expected ? { status: "critical", label: "To'xtagan" } : { status: "warning", label: "To'xtagan" };
}

export function ContainersTab({ serverId }: { serverId: string }) {
  const q = useContainers(serverId);
  const now = useNow();
  if (q.isPending) return <SkeletonRows rows={4} className="h-10" />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Konteynerlarni yuklab bo'lmadi" />;
  const items = q.data ?? [];
  if (items.length === 0) return <EmptyState title="Konteyner topilmadi" hint="Agent Docker ma'lumotini yuborsa, konteynerlar shu yerda ko'rinadi." />;
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-left">
        <caption className="sr-only">Konteynerlar ro&apos;yxati</caption>
        <thead>
          <tr className="border-b border-line text-[13px] text-muted">
            <th scope="col" className="px-3 py-2 font-medium">Nom</th>
            <th scope="col" className="px-3 py-2 font-medium">Loyiha</th>
            <th scope="col" className="px-3 py-2 font-medium">Servis</th>
            <th scope="col" className="px-3 py-2 font-medium">Holat</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Restartlar</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Uptime</th>
            <th scope="col" className="px-3 py-2 font-medium">Health</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => {
            const st = containerStatus(c);
            const health = c.health != null ? HEALTH[c.health] : null;
            return (
              <tr key={c.container} className={`border-b border-line last:border-0 ${c.stale ? "bg-surface-2 text-muted" : ""}`}>
                <th scope="row" className="px-3 py-2 font-medium">
                  <span className="mono">{c.container}</span>
                  {c.expected ? <span className="ml-2 text-xs font-normal text-muted">kutilgan</span> : null}
                </th>
                <td className="px-3 py-2">{c.project || "—"}</td>
                <td className="px-3 py-2">{c.service || "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={st.status} label={st.label} size="sm" />
                    {c.stale && <StaleChip />}
                    {!c.stale && c.oom_killed ? <StatusBadge status="high" label="OOM" size="sm" /> : null}
                  </div>
                  {c.stale && <p className="mt-0.5 text-xs">oxirgi: {formatAgoFrom(c.time, now)}</p>}
                </td>
                <td className="num px-3 py-2 text-right">{c.stale ? "—" : formatNumber(c.restarts ?? 0, 0)}</td>
                <td className="num px-3 py-2 text-right">{c.stale || !c.running ? "—" : formatDuration(c.uptime_seconds)}</td>
                <td className="px-3 py-2">{c.stale || !health ? "—" : <StatusBadge status={health.status} label={health.label} size="sm" />}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
