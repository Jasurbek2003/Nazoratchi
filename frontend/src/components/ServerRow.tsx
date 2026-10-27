import { memo, useMemo } from "react";
import { Link } from "react-router-dom";
import { useLatest, useSpark } from "../api/queries";
import type { Incident, Server } from "../api/types";
import { sparkValues } from "../lib/chart";
import { formatPercent } from "../lib/format";
import { serverDisplayStatus, extractVitals } from "../lib/serverStatus";
import { useNow } from "../lib/useNow";
import { FreshnessLabel, GaugeBar } from "./Indicators";
import { Sparkline } from "./Sparkline";
import { StatusBadge, STATUS_CLASS } from "./Status";

/** Server qatori (Dashboard va /servers): holat + CPU/RAM/disk + CPU sparkline. Mobilda ustun bo'lib yig'iladi. */
export const ServerRow = memo(function ServerRow({ server, incidents, tz }: { server: Server; incidents: Incident[]; tz?: string | null }) {
  const now = useNow();
  const active = server.status === "online" || server.status === "offline";
  const latest = useLatest(server.id, active);
  const spark = useSpark(server.id, active);
  const display = serverDisplayStatus(server, incidents, now);
  const vitals = useMemo(() => extractVitals(latest.data, now), [latest.data, now]);
  const values = useMemo(() => sparkValues(spark.data?.series[0]?.points), [spark.data]);
  // Server eskirgan bo'lsa, metrikalar ham "hozirgi" emas.
  const stale = display.stale;
  const loadingMetrics = active && latest.isPending;

  return (
    <li className="panel relative grid items-center gap-x-4 grid-cols-2 gap-y-3 py-3 pl-4 pr-3 hover:bg-surface-2 md:grid-cols-[minmax(200px,1.3fr)_minmax(180px,1.2fr)_repeat(2,minmax(90px,.55fr))_minmax(130px,.8fr)]">
      <span className={`absolute inset-y-0 left-0 w-1 rounded-l-[10px] ${STATUS_CLASS[display.status].bar}`} aria-hidden />
      <div className="col-span-2 min-w-0 md:col-span-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link to={`/servers/${server.id}`} className="font-semibold after:absolute after:inset-0 after:content-['']">
            {server.name}
          </Link>
          <StatusBadge status={display.status} label={display.label} size="sm" />
        </div>
        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[13px] text-muted">
          <span className="mono">{server.public_ipv4 ?? server.public_ipv6 ?? "IP yo'q"}</span>
          {server.tags.slice(0, 4).map((t) => (
            <span key={t} className="rounded bg-surface-2 px-1.5 text-xs leading-5 ring-1 ring-line">
              {t}
            </span>
          ))}
        </div>
      </div>

      {loadingMetrics ? (
        <div className="skeleton col-span-2 h-9 md:col-span-3" aria-label="Ko'rsatkichlar yuklanmoqda" role="status" />
      ) : (
        <>
          <div className="col-span-2 flex items-center gap-3 md:col-span-1">
            <div className="min-w-0 flex-1">
              <GaugeBar label="CPU" value={vitals.cpu?.value} stale={stale || vitals.cpu?.stale || !vitals.cpu} compact />
            </div>
            <Sparkline values={values} stale={stale} width={72} height={26} />
          </div>
          <GaugeBar label="RAM" value={vitals.mem?.value} stale={stale || vitals.mem?.stale || !vitals.mem} compact />
          <div title={vitals.disk?.detail ? `Eng to'lgan: ${vitals.disk.detail} (${formatPercent(vitals.disk.value)})` : undefined}>
            <GaugeBar label="Disk" value={vitals.disk?.value} stale={stale || vitals.disk?.stale || !vitals.disk} compact />
          </div>
        </>
      )}

      <div className="col-span-2 text-[13px] md:col-span-1 md:text-right">
        <FreshnessLabel iso={server.last_seen_at} now={now} tz={tz} prefix="aloqa: " />
      </div>
    </li>
  );
});
