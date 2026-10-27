import { memo, useId, useState } from "react";
import { Link } from "react-router-dom";
import { useAckIncident, useIncidentDetail } from "../api/queries";
import type { Incident, Role } from "../api/types";
import { describeEvent, scopeLabel } from "../lib/incident";
import { ageSeconds, formatAgo, formatDateTime } from "../lib/format";
import { hostOf } from "../lib/summary";
import { severityStatus, STATUS_META } from "../lib/status";
import { ErrorState, SkeletonRows } from "./Feedback";
import { StatusBadge, STATUS_CLASS, StatusIcon } from "./Status";

/**
 * Incident kartochkasi, joyida kengayadi (incident sahifasi keyingi sprintda): alertlar va voqealar
 * `GET /incidents/:id` dan. "Qabul qilaman" faqat owner/operator uchun.
 */
export const IncidentCard = memo(function IncidentCard({
  incident,
  now,
  serverName,
  role,
  tz,
}: {
  incident: Incident;
  now: number;
  serverName?: string;
  role: Role;
  tz?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const status = severityStatus(incident.severity);
  const detail = useIncidentDetail(incident.id, open);
  const ack = useAckIncident();
  const hostId = hostOf(incident);
  const canAck = role !== "viewer" && incident.status === "open";
  const age = ageSeconds(incident.started_at, now);

  return (
    <article className="panel overflow-hidden" data-testid="incident-card" data-severity={incident.severity}>
      <div className="flex items-stretch">
        <span className={`w-1.5 shrink-0 ${STATUS_CLASS[status].bar}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <button
            type="button"
            className="flex w-full items-start gap-3 px-3 py-3 text-left max-md:min-h-11"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
          >
            <span className={`mt-0.5 ${STATUS_CLASS[status].text}`}>
              <StatusIcon status={status} size={18} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold leading-snug">{incident.title}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
                <span className={`font-medium ${STATUS_CLASS[status].text}`}>{STATUS_META[status].label}</span>
                <span>{scopeLabel(incident.scope_key, serverName)}</span>
                <span className="num" title={formatDateTime(incident.started_at, tz)}>
                  {age == null ? "" : formatAgo(age)}
                </span>
                {incident.status === "acknowledged" && <span>Qabul qilingan{incident.acked_by ? `: ${incident.acked_by}` : ""}</span>}
                {incident.suppressed && <span>Bostirilgan</span>}
              </span>
            </span>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden className={`mt-1 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}>
              <path d="M3 6l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          <div className="flex flex-wrap items-center gap-2 px-3 pb-3 pl-[42px]">
            {canAck && (
              <button type="button" className="btn btn-primary" disabled={ack.isPending} onClick={() => ack.mutate(incident.id)}>
                {ack.isPending ? "Qabul qilinmoqda…" : "Qabul qilaman"}
              </button>
            )}
            {hostId && (
              <Link className="btn" to={`/servers/${hostId}`}>
                Serverni ochish
              </Link>
            )}
            {ack.isError && (
              <span role="alert" className="text-critical-fg">
                {ack.error.message}
              </span>
            )}
          </div>

          {open && (
            <div id={panelId} className="border-t border-line bg-surface-2 px-4 py-3">
              {detail.isPending ? (
                <SkeletonRows rows={2} className="h-8" />
              ) : detail.error ? (
                <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  <section aria-label="Alertlar">
                    <h3 className="mb-1.5 text-[13px] font-semibold">Alertlar ({detail.data.alerts.length})</h3>
                    {detail.data.alerts.length === 0 ? (
                      <p className="text-muted">Alert yo&apos;q.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {detail.data.alerts.map((a) => (
                          <li key={a.id} className="flex flex-wrap items-center gap-2">
                            <StatusBadge status={severityStatus(a.severity)} size="sm" />
                            <span className="font-medium">{a.rule_name}</span>
                            <span className="text-muted">{a.subject_name}</span>
                            <span className="text-muted">· {a.state === "firing" ? "faol" : a.state === "pending" ? "kutilmoqda" : a.state === "resolving" ? "tiklanmoqda" : "joyida"}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                  <section aria-label="Voqealar">
                    <h3 className="mb-1.5 text-[13px] font-semibold">Voqealar ({detail.data.events.length})</h3>
                    {detail.data.events.length === 0 ? (
                      <p className="text-muted">Voqea yo&apos;q.</p>
                    ) : (
                      <ol className="space-y-1">
                        {detail.data.events.map((e) => (
                          <li key={e.id} className="flex gap-2">
                            <time className="num shrink-0 text-muted" dateTime={e.time}>
                              {formatDateTime(e.time, tz).slice(5)}
                            </time>
                            <span>{describeEvent(e)}</span>
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                  {detail.data.root_cause && (
                    <p className="md:col-span-2">
                      <span className="font-semibold">Sabab: </span>
                      {detail.data.root_cause}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
});
