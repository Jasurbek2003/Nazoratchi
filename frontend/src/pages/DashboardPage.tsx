import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useAlerts, useCerts, useServers, useUnresolvedIncidents } from "../api/queries";
import type { AlertInstance, Incident, Server } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/Feedback";
import { IncidentCard } from "../components/IncidentCard";
import { CertBadge, StaleChip } from "../components/Indicators";
import { ServerRow } from "../components/ServerRow";
import { STATUS_CLASS, StatusIcon } from "../components/Status";
import { ageSeconds, formatAgo, formatDateTime } from "../lib/format";
import { STALE_AFTER_S } from "../lib/freshness";
import { buildSummary, hostOf, type Summary } from "../lib/summary";
import { severityStatus, worstStatus } from "../lib/status";
import { useNow } from "../lib/useNow";

export function countServers(servers: Server[]): { online: number; offline: number; paused: number; fresh: number } {
  let online = 0,
    offline = 0,
    paused = 0;
  for (const s of servers) {
    if (s.status === "online") online += 1;
    else if (s.status === "offline") offline += 1;
    else if (s.status === "paused") paused += 1;
  }
  return { online, offline, paused, fresh: servers.length - online - offline - paused };
}

function Banner({ summary, servers, stale, ageLabel }: { summary: Summary; servers: Server[]; stale: boolean; ageLabel: string }) {
  const c = countServers(servers);
  const level = summary.level;
  const ok = summary.problems.length === 0;
  const parts = [
    `${c.online} server onlayn`,
    c.offline ? `${c.offline} aloqada emas` : null,
    c.paused ? `${c.paused} pauzada` : null,
    c.fresh ? `${c.fresh} yangi` : null,
    summary.suppressed ? `${summary.suppressed} ta incident bostirilgan` : null,
  ].filter(Boolean);
  return (
    <section
      aria-label="Umumiy holat"
      aria-live="polite"
      data-level={level}
      className={`relative overflow-hidden rounded-[10px] border px-5 py-5 md:px-7 md:py-6 ${STATUS_CLASS[level].chip}`}
    >
      <span className={`absolute inset-y-0 left-0 w-2 ${STATUS_CLASS[level].bar}`} aria-hidden />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pl-2">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full border-2 border-current">
          <StatusIcon status={level} size={26} />
        </span>
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight md:text-[32px]">{summary.headline}</h1>
          <p className="mt-0.5 text-[14px] opacity-90 num">{parts.join(" · ")}</p>
        </div>
        {stale && (
          <p className="ml-auto flex items-center gap-2 rounded-md bg-surface/70 px-3 py-1.5 text-[13px] font-medium text-warning-fg">
            <StaleChip />
            Ma&apos;lumot {ageLabel} yangilangan
          </p>
        )}
        {ok && !stale && <p className="ml-auto hidden text-[13px] opacity-80 md:block">Ochiq incident yo&apos;q</p>}
      </div>
    </section>
  );
}

function AlertsPanel({ alerts }: { alerts: AlertInstance[] | undefined }) {
  const firing = alerts?.filter((a) => a.state === "firing" && !a.suppressed) ?? [];
  const pending = alerts?.filter((a) => a.state === "pending") ?? [];
  const suppressed = alerts?.filter((a) => a.state === "firing" && a.suppressed).length ?? 0;
  const worst = worstStatus(firing.map((a) => severityStatus(a.severity)));
  return (
    <section className="panel p-4" aria-labelledby="alerts-h">
      <h2 id="alerts-h" className="text-[15px] font-semibold">
        Ochiq alertlar
      </h2>
      {!alerts ? (
        <Skeleton className="mt-3 h-10" />
      ) : (
        <div className="mt-2 flex items-baseline gap-3">
          <span className={`text-4xl font-semibold num ${firing.length ? STATUS_CLASS[worst].text : "text-ok-fg"}`}>{firing.length}</span>
          <span className="text-muted">
            faol{pending.length ? ` · ${pending.length} kutilmoqda` : ""}
            {suppressed ? ` · ${suppressed} bostirilgan` : ""}
          </span>
        </div>
      )}
    </section>
  );
}

function CertsPanel({ tz }: { tz: string }) {
  const certs = useCerts({ days_left_lt: 30 });
  return (
    <section className="panel p-4" aria-labelledby="certs-h">
      <h2 id="certs-h" className="text-[15px] font-semibold">
        Sertifikat muddatlari
      </h2>
      <p className="text-[13px] text-muted">30 kun ichida tugaydiganlar</p>
      <div className="mt-3">
        {certs.isPending ? (
          <SkeletonRows rows={2} className="h-8" />
        ) : certs.error ? (
          <ErrorState error={certs.error} onRetry={() => void certs.refetch()} title="Sertifikatlarni yuklab bo'lmadi" />
        ) : certs.data.length === 0 ? (
          <p className="text-muted">Yaqin 30 kunda muddati tugaydigan sertifikat yo&apos;q.</p>
        ) : (
          <ul className="divide-y divide-line">
            {certs.data.slice(0, 8).map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="truncate font-medium" title={c.name}>
                    {c.name}
                  </p>
                  <p className="truncate text-xs text-muted" title={`Tugaydi: ${formatDateTime(c.not_after, tz)}`}>
                    {c.project ?? "loyihasiz"}
                  </p>
                </div>
                <CertBadge daysLeft={c.days_left} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function DashboardPage() {
  usePageTitle("Bosh sahifa");
  const me = useCurrentUser();
  const now = useNow();
  const servers = useServers();
  const incidents = useUnresolvedIncidents();
  const alerts = useAlerts();

  const serverById = useMemo(() => new Map((servers.data ?? []).map((s) => [s.id, s])), [servers.data]);
  const summary = useMemo(
    () => (servers.data && incidents.data ? buildSummary({ incidents: incidents.data, servers: servers.data, now }) : null),
    [servers.data, incidents.data, now],
  );
  const incidentsByHost = useMemo(() => {
    const m = new Map<string, Incident[]>();
    for (const i of incidents.data ?? []) {
      const h = hostOf(i);
      if (h) m.set(h, [...(m.get(h) ?? []), i]);
    }
    return m;
  }, [incidents.data]);

  const loadError = servers.error ?? incidents.error;
  const incUpdatedAge = incidents.dataUpdatedAt ? (now - incidents.dataUpdatedAt) / 1000 : null;
  const dataStale = incUpdatedAge != null && incUpdatedAge > STALE_AFTER_S;
  const ageLabel = incUpdatedAge != null ? formatAgo(incUpdatedAge) : "";

  return (
    <div className="space-y-6">
      {loadError && !summary ? (
        <div>
          <ErrorState
            error={loadError}
            title="Holatni aniqlab bo'lmadi"
            onRetry={() => {
              void servers.refetch();
              void incidents.refetch();
            }}
          />
          <p className="mt-2 text-muted">Ma&apos;lumot kelmaguncha &quot;hammasi joyida&quot; deb hisoblanmaydi.</p>
        </div>
      ) : !summary ? (
        <Skeleton className="h-24 w-full" label="Umumiy holat yuklanmoqda" />
      ) : servers.data!.length === 0 ? (
        <EmptyState title="Hali nazorat qilinadigan server yo'q" hint="Server ulangach, uning holati va muammolari shu yerda ko'rinadi." />
      ) : (
        <Banner summary={summary} servers={servers.data!} stale={dataStale || !!loadError} ageLabel={ageLabel} />
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          {summary && summary.problems.length > 0 && (
            <section aria-labelledby="problems-h" className="space-y-2">
              <h2 id="problems-h" className="text-[15px] font-semibold">
                Muammolar ({summary.problems.length})
              </h2>
              <div className="space-y-2">
                {summary.problems.map((p) =>
                  p.incident ? (
                    <IncidentCard
                      key={p.key}
                      incident={p.incident}
                      now={now}
                      serverName={p.serverId ? serverById.get(p.serverId)?.name : undefined}
                      role={me.role}
                      tz={me.timezone}
                    />
                  ) : (
                    <Link
                      key={p.key}
                      to={`/servers/${p.serverId}`}
                      className={`panel flex items-center gap-3 border-l-4 px-3 py-3 max-md:min-h-11 ${p.status === "critical" ? "border-l-critical" : "border-l-unknown"}`}
                    >
                      <span className={STATUS_CLASS[p.status].text}>
                        <StatusIcon status={p.status} size={18} />
                      </span>
                      <span className="font-semibold">{p.title}</span>
                      <span className="ml-auto text-[13px] text-muted num">
                        {p.since ? `oxirgi aloqa: ${formatAgo(ageSeconds(p.since, now))}` : "aloqa bo'lmagan"}
                      </span>
                    </Link>
                  ),
                )}
              </div>
            </section>
          )}

          <section aria-labelledby="servers-h" className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 id="servers-h" className="text-[15px] font-semibold">
                Serverlar{servers.data ? ` (${servers.data.length})` : ""}
              </h2>
              <Link to="/servers" className="font-medium text-accent underline-offset-2 hover:underline">
                Hammasi
              </Link>
            </div>
            {servers.isPending ? (
              <SkeletonRows rows={3} className="h-[76px]" />
            ) : servers.error && !servers.data ? (
              <ErrorState error={servers.error} onRetry={() => void servers.refetch()} title="Serverlarni yuklab bo'lmadi" />
            ) : (
              <ul className="m-0 list-none space-y-2 p-0">
                {servers.data!.map((s) => (
                  <ServerRow key={s.id} server={s} incidents={incidentsByHost.get(s.id) ?? []} tz={me.timezone} />
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="space-y-4" aria-label="Qo'shimcha ma'lumot">
          <AlertsPanel alerts={alerts.data} />
          <CertsPanel tz={me.timezone} />
        </aside>
      </div>
    </div>
  );
}
