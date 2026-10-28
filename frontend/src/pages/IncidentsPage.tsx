import { memo, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAckIncident, useIncidentList, useServers } from "../api/queries";
import type { Incident, IncidentStatus, Role } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { PageHeader } from "../components/FormField";
import { StatusBadge, STATUS_CLASS, StatusIcon } from "../components/Status";
import { scopeLabel } from "../lib/incident";
import { ageSeconds, formatAgo, formatDateTime } from "../lib/format";
import { severityStatus, STATUS_META } from "../lib/status";
import { useNow } from "../lib/useNow";

export const INCIDENT_STATUS_LABEL: Record<IncidentStatus, string> = { open: "Ochiq", acknowledged: "Qabul qilingan", resolved: "Hal qilingan" };

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Hamma holat" },
  { value: "open", label: "Ochiq" },
  { value: "acknowledged", label: "Qabul qilingan" },
  { value: "resolved", label: "Hal qilingan" },
];
const SEVERITY_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Hamma ahamiyat" },
  { value: "critical", label: "Kritik" },
  { value: "high", label: "Muhim" },
  { value: "warning", label: "Diqqat" },
  { value: "info", label: "Ma'lumot" },
];

const Row = memo(function Row({ incident, now, serverName, role, tz }: { incident: Incident; now: number; serverName?: string; role: Role; tz: string }) {
  const sev = severityStatus(incident.severity);
  const ack = useAckIncident();
  const age = ageSeconds(incident.started_at, now);
  const canAck = role !== "viewer" && incident.status === "open";
  return (
    <li data-testid="incident-row" className="panel relative flex items-stretch overflow-hidden">
      <span className={`w-1.5 shrink-0 ${STATUS_CLASS[sev].bar}`} aria-hidden />
      <div className="min-w-0 flex-1 px-3 py-3">
        <div className="flex items-start gap-2">
          <span className={`mt-0.5 ${STATUS_CLASS[sev].text}`}>
            <StatusIcon status={sev} size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <Link to={`/incidents/${incident.id}`} className="block font-semibold leading-snug hover:underline">
              {incident.title}
            </Link>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
              <span className={`font-medium ${STATUS_CLASS[sev].text}`}>{STATUS_META[sev].label}</span>
              <span>{scopeLabel(incident.scope_key, serverName)}</span>
              <span className="num" title={formatDateTime(incident.started_at, tz)}>
                {age == null ? "" : formatAgo(age)}
              </span>
              {incident.suppressed && <span>Bostirilgan</span>}
            </p>
          </div>
          <StatusBadge status={incident.status === "resolved" ? "ok" : incident.status === "acknowledged" ? "info" : "critical"} label={INCIDENT_STATUS_LABEL[incident.status]} size="sm" />
        </div>
        {(canAck || ack.isError) && (
          <div className="mt-2 flex flex-wrap items-center gap-2 pl-[26px]">
            {canAck && (
              <button type="button" className="btn btn-primary" disabled={ack.isPending} onClick={() => ack.mutate(incident.id)}>
                {ack.isPending ? "Qabul qilinmoqda…" : "Qabul qilaman"}
              </button>
            )}
            {ack.isError && (
              <span role="alert" className="text-critical-fg">
                {ack.error.message}
              </span>
            )}
          </div>
        )}
      </div>
    </li>
  );
});

export default function IncidentsPage() {
  usePageTitle("Incidentlar");
  const me = useCurrentUser();
  const now = Math.floor(useNow() / 15_000) * 15_000;
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const severity = params.get("severity") ?? "";
  const list = useIncidentList({ status: status || undefined, severity: severity || undefined });
  const servers = useServers();
  const names = useMemo(() => new Map((servers.data ?? []).map((s) => [s.id, s.name])), [servers.data]);
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Incidentlar">
        <p className="text-muted num" aria-live="polite">
          {list.data ? `${items.length} ta${list.hasNextPage ? "+" : ""}` : ""}
        </p>
      </PageHeader>

      <form role="search" aria-label="Incidentlarni filtrlash" className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => e.preventDefault()}>
        <div>
          <label htmlFor="inc-status" className="sr-only">
            Holat
          </label>
          <select id="inc-status" className="field" value={status} onChange={(e) => set("status", e.target.value)}>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="inc-sev" className="sr-only">
            Ahamiyat
          </label>
          <select id="inc-sev" className="field" value={severity} onChange={(e) => set("severity", e.target.value)}>
            {SEVERITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn" disabled={!status && !severity} onClick={() => setParams({}, { replace: true })}>
          Tozalash
        </button>
      </form>

      {list.isPending ? (
        <SkeletonRows rows={5} className="h-[72px]" />
      ) : list.error && !list.data ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} title="Incidentlarni yuklab bo'lmadi" />
      ) : items.length === 0 ? (
        <EmptyState title={status || severity ? "Hech narsa topilmadi" : "Incident yo'q"} hint={status || severity ? "Filtr shartiga mos incident yo'q." : "Hozircha hech qanday muammo qayd etilmagan."} />
      ) : (
        <>
          <ul className="m-0 list-none space-y-2 p-0">
            {items.map((i) => (
              <Row key={i.id} incident={i} now={now} role={me.role} tz={me.timezone} serverName={i.scope_key.startsWith("host:") ? names.get(i.scope_key.slice(5)) : undefined} />
            ))}
          </ul>
          {list.hasNextPage && (
            <div className="text-center">
              <button type="button" className="btn" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
                {list.isFetchingNextPage ? "Yuklanmoqda…" : "Yana ko'rsatish"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
