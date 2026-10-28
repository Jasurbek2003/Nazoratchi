import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAckIncident, useIncidentComment, useIncidentDetail, useResolveIncident, useServers } from "../api/queries";
import { useCurrentUser, usePageTitle } from "../app/context";
import { ConfirmDialog } from "../components/Controls";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/Feedback";
import { StatusBadge, STATUS_CLASS, StatusIcon } from "../components/Status";
import { describeEvent, scopeLabel } from "../lib/incident";
import { ageSeconds, formatDateTime, formatDuration } from "../lib/format";
import { hostOf } from "../lib/summary";
import { severityStatus, STATUS_META } from "../lib/status";
import { useNow } from "../lib/useNow";
import { INCIDENT_STATUS_LABEL } from "./IncidentsPage";

const ALERT_STATE: Record<string, string> = { firing: "faol", pending: "kutilmoqda", resolving: "tiklanmoqda", ok: "joyida" };
const MAX_COMMENT = 2000;

export default function IncidentPage() {
  const { id = "" } = useParams();
  const me = useCurrentUser();
  const now = useNow();
  const detail = useIncidentDetail(id, true);
  const servers = useServers();
  const ack = useAckIncident();
  const comment = useIncidentComment(id);
  const resolve = useResolveIncident(id);
  const [text, setText] = useState("");
  const [confirmResolve, setConfirmResolve] = useState(false);
  usePageTitle(detail.data?.title ?? "Incident");

  if (detail.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16" label="Incident yuklanmoqda" />
        <SkeletonRows rows={2} className="h-24" />
      </div>
    );
  }
  if (detail.error && !detail.data) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404;
    return notFound ? (
      <EmptyState
        title="Incident topilmadi"
        hint="Bu incident mavjud emas yoki manzil noto'g'ri."
        action={
          <Link className="btn btn-primary" to="/incidents">
            Incidentlar ro&apos;yxatiga qaytish
          </Link>
        }
      />
    ) : (
      <ErrorState error={detail.error} onRetry={() => void detail.refetch()} title="Incidentni yuklab bo'lmadi" />
    );
  }

  const inc = detail.data!;
  const sev = severityStatus(inc.severity);
  const canWrite = me.role !== "viewer";
  const hostId = hostOf(inc);
  const serverName = hostId ? servers.data?.find((s) => s.id === hostId)?.name : undefined;
  const endMs = inc.resolved_at ? Date.parse(inc.resolved_at) : now;
  const lasted = ageSeconds(inc.started_at, endMs);
  const trimmed = text.trim();
  const tooLong = text.length > MAX_COMMENT;

  const submitComment = (e: FormEvent) => {
    e.preventDefault();
    if (!trimmed || tooLong) return;
    comment.mutate(trimmed, { onSuccess: () => setText("") });
  };

  return (
    <div className="space-y-4">
      <nav aria-label="Joylashuv" className="text-[13px] text-muted">
        <Link to="/incidents" className="hover:text-ink hover:underline">
          Incidentlar
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{inc.title}</span>
      </nav>

      <header className="panel p-4">
        <div className="flex flex-wrap items-start gap-3">
          <span className={`mt-1 ${STATUS_CLASS[sev].text}`}>
            <StatusIcon status={sev} size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold leading-tight tracking-tight">{inc.title}</h1>
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-muted">
              <span>{scopeLabel(inc.scope_key, serverName)}</span>
              <span>Ahamiyat: {STATUS_META[sev].label.toLowerCase()}</span>
              <span className="num">Boshlangan: {formatDateTime(inc.started_at, me.timezone)}</span>
              <span className="num">
                Davomiyligi: {formatDuration(lasted)}
                {!inc.resolved_at && " (davom etmoqda)"}
              </span>
            </p>
          </div>
          <StatusBadge status={inc.status === "resolved" ? "ok" : inc.status === "acknowledged" ? "info" : "critical"} label={INCIDENT_STATUS_LABEL[inc.status]} />
        </div>
        {inc.status === "acknowledged" && inc.acked_by && (
          <p className="mt-2 text-muted num">
            Qabul qildi: {inc.acked_by}, {formatDateTime(inc.acked_at, me.timezone)}
          </p>
        )}
        {inc.suppressed && <p className="mt-2 text-muted">Bu incident bostirilgan (silence yoki texnik ish): bildirishnoma yuborilmaydi.</p>}
        {inc.root_cause && (
          <p className="mt-2">
            <span className="font-semibold">Sabab: </span>
            {inc.root_cause}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {canWrite && inc.status === "open" && (
            <button type="button" className="btn btn-primary" disabled={ack.isPending} onClick={() => ack.mutate(inc.id)}>
              {ack.isPending ? "Qabul qilinmoqda…" : "Qabul qilaman"}
            </button>
          )}
          {canWrite && inc.status !== "resolved" && (
            <button type="button" className="btn" onClick={() => setConfirmResolve(true)}>
              Qo&apos;lda yopish
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
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-4" aria-labelledby="ev-h">
          <h2 id="ev-h" className="mb-2 text-[15px] font-semibold">
            Vaqt chizig&apos;i ({inc.events.length})
          </h2>
          {inc.events.length === 0 ? (
            <p className="text-muted">Voqea yo&apos;q.</p>
          ) : (
            <ol className="space-y-1.5">
              {inc.events.map((e) => (
                <li key={e.id} className="flex gap-2">
                  <time className="num shrink-0 text-muted" dateTime={e.time}>
                    {formatDateTime(e.time, me.timezone).slice(5)}
                  </time>
                  <span className="min-w-0 break-words">{describeEvent(e)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel p-4" aria-labelledby="al-h">
          <h2 id="al-h" className="mb-2 text-[15px] font-semibold">
            Alertlar ({inc.alerts.length})
          </h2>
          {inc.alerts.length === 0 ? (
            <p className="text-muted">Alert yo&apos;q.</p>
          ) : (
            <ul className="space-y-2">
              {inc.alerts.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={severityStatus(a.severity)} size="sm" />
                  <span className="font-medium">{a.rule_name}</span>
                  <span className="text-muted">{a.subject_name}</span>
                  <span className="text-muted">· {ALERT_STATE[a.state] ?? a.state}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {canWrite ? (
          <section className="panel p-4 lg:col-span-2" aria-labelledby="cm-h">
            <h2 id="cm-h" className="mb-2 text-[15px] font-semibold">
              Izoh yozish
            </h2>
            <form onSubmit={submitComment} className="space-y-2">
              <label htmlFor="inc-comment" className="sr-only">
                Izoh matni
              </label>
              <textarea
                id="inc-comment"
                className="field min-h-20"
                value={text}
                maxLength={MAX_COMMENT + 100}
                aria-invalid={tooLong}
                aria-describedby={tooLong ? "inc-comment-err" : undefined}
                onChange={(e) => setText(e.target.value)}
                placeholder="Masalan: provayder panelida restart berdim"
              />
              {tooLong && (
                <p id="inc-comment-err" role="alert" className="text-critical-fg">
                  Izoh {MAX_COMMENT} belgidan oshmasligi kerak.
                </p>
              )}
              {comment.isError && (
                <p role="alert" className="text-critical-fg">
                  {comment.error.message}
                </p>
              )}
              <button type="submit" className="btn btn-primary" disabled={!trimmed || tooLong || comment.isPending}>
                {comment.isPending ? "Qo'shilmoqda…" : "Qo'shish"}
              </button>
            </form>
          </section>
        ) : (
          <p className="text-muted lg:col-span-2">Kuzatuvchi roli izoh yozish va incidentni boshqarish huquqiga ega emas.</p>
        )}
      </div>

      <ConfirmDialog
        open={confirmResolve}
        title="Incidentni qo'lda yopasizmi?"
        confirmLabel="Yopish"
        busy={resolve.isPending}
        error={resolve.isError ? resolve.error.message : null}
        onCancel={() => setConfirmResolve(false)}
        onConfirm={() => resolve.mutate(undefined, { onSuccess: () => setConfirmResolve(false) })}
      >
        <p>Incident hal qilingan deb belgilanadi. Sabab yo&apos;qolmagan bo&apos;lsa, alert qayta yuzaga kelganda yangi incident ochiladi.</p>
      </ConfirmDialog>
    </div>
  );
}
