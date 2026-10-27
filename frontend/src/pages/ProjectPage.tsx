import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useCerts, useProbes, useProject } from "../api/queries";
import type { Cert, Probe } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/Feedback";
import { CertBadge, StaleChip } from "../components/Indicators";
import { StatusBadge } from "../components/Status";
import { formatAgoFrom, formatDateTime, formatNumber } from "../lib/format";
import { effectiveProbeStatus, KIND_LABEL, probeStale, projectHealth } from "../lib/projectStatus";
import { PROBE_STATE_LABEL } from "../lib/status";
import { useNow } from "../lib/useNow";
import { ProjectBadges } from "./ProjectsPage";

/** Faqat http(s) havolalar (javascript: va boshqa sxemalar rad etiladi). */
export function safeHref(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

const PROBE_TYPE: Record<Probe["type"], string> = { http: "HTTP", tcp: "TCP", tls: "TLS", dns: "DNS", whois: "WHOIS" };

function probeLabel(p: Probe, now: number): string {
  if (!p.enabled) return "O'chirilgan";
  if (probeStale(p, now)) return "Eskirgan";
  return PROBE_STATE_LABEL[p.state] ?? p.state;
}

function ProbesTable({ probes, now, tz }: { probes: Probe[]; now: number; tz: string }) {
  if (probes.length === 0) return <p className="text-muted">Bu loyiha uchun tekshiruv sozlanmagan.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] border-collapse text-left">
        <caption className="sr-only">Tekshiruvlar holati</caption>
        <thead>
          <tr className="border-b border-line text-[13px] text-muted">
            <th scope="col" className="py-2 pr-3 font-medium">Tekshiruv</th>
            <th scope="col" className="py-2 pr-3 font-medium">Tur</th>
            <th scope="col" className="py-2 pr-3 font-medium">Holat</th>
            <th scope="col" className="py-2 pr-3 font-medium">Oxirgi natija</th>
            <th scope="col" className="py-2 font-medium">Oxirgi tekshiruv</th>
          </tr>
        </thead>
        <tbody>
          {probes.map((p) => {
            const stale = probeStale(p, now);
            const r = p.last_result;
            return (
              <tr key={p.id} className="border-b border-line last:border-0">
                <th scope="row" className="py-2 pr-3 font-medium">
                  {p.name}
                </th>
                <td className="py-2 pr-3">{PROBE_TYPE[p.type]}</td>
                <td className="py-2 pr-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={effectiveProbeStatus(p, now)} label={probeLabel(p, now)} size="sm" />
                    {stale && <StaleChip />}
                  </div>
                </td>
                <td className={`num py-2 pr-3 ${stale ? "text-muted" : ""}`}>
                  {r ? (
                    <>
                      {r.status_code ?? (r.ok ? "OK" : r.error_kind ?? "xato")}
                      {r.total_ms != null && ` · ${formatNumber(r.total_ms, 0)} ms`}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="num py-2 text-muted" title={formatDateTime(p.last_run_at, tz)}>
                  {formatAgoFrom(p.last_run_at, now)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function ProjectPage() {
  const { id = "" } = useParams();
  const me = useCurrentUser();
  const now = useNow();
  const project = useProject(id);
  const probes = useProbes(id);
  const certs = useCerts({ project_id: id });
  usePageTitle(project.data?.name ?? "Loyiha");

  const certByDomain = useMemo(() => {
    const m = new Map<string, Cert[]>();
    for (const c of certs.data ?? []) if (c.domain) m.set(c.domain, [...(m.get(c.domain) ?? []), c]);
    return m;
  }, [certs.data]);
  const probesByDomain = useMemo(() => {
    const m = new Map<string, Probe[]>();
    for (const p of probes.data ?? []) if (p.domain) m.set(p.domain, [...(m.get(p.domain) ?? []), p]);
    return m;
  }, [probes.data]);

  if (project.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16" label="Loyiha yuklanmoqda" />
        <SkeletonRows rows={3} className="h-24" />
      </div>
    );
  }
  if (project.error && !project.data) {
    const notFound = project.error instanceof ApiError && project.error.status === 404;
    return notFound ? (
      <EmptyState
        title="Loyiha topilmadi"
        hint="Bu loyiha mavjud emas yoki manzil noto'g'ri."
        action={
          <Link className="btn btn-primary" to="/projects">
            Loyihalar ro&apos;yxatiga qaytish
          </Link>
        }
      />
    ) : (
      <ErrorState error={project.error} onRetry={() => void project.refetch()} title="Loyihani yuklab bo'lmadi" />
    );
  }

  const p = project.data!;
  const health = projectHealth(p, probes.data ?? [], now);

  return (
    <div className="space-y-4">
      <nav aria-label="Joylashuv" className="text-[13px] text-muted">
        <Link to="/projects" className="hover:text-ink hover:underline">
          Loyihalar
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{p.name}</span>
      </nav>

      <header className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
          <StatusBadge status={health.status} label={health.label} />
          <ProjectBadges project={p} />
        </div>
        <p className="mt-1 flex flex-wrap gap-x-3 text-muted">
          <span className="mono">{p.slug}</span>
          <span>{KIND_LABEL[p.kind]}</span>
          {p.owner_name && <span>egasi: {p.owner_name}</span>}
          {p.tags.length > 0 && <span>{p.tags.join(", ")}</span>}
        </p>
        {p.description && <p className="mt-2 max-w-3xl">{p.description}</p>}
        {!p.moved && <p className="mt-2 text-warning-fg">Loyiha hali yangi serverga ko&apos;chirilmagan: tekshiruvlar sozlanmagan bo&apos;lishi mumkin.</p>}
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-4" aria-labelledby="srv-h">
          <h2 id="srv-h" className="text-[15px] font-semibold">
            Serverlar va portlar
          </h2>
          {p.servers_info.length === 0 ? (
            <p className="mt-2 text-muted">Server biriktirilmagan.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {p.servers_info.map((s) => (
                <li key={`${s.server_id}-${s.environment}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <Link to={`/servers/${s.server_id}`} className="font-medium text-accent hover:underline">
                    {s.server}
                  </Link>
                  <span className="text-[13px] text-muted">
                    {s.environment}
                    {s.ports.length > 0 && <span className="mono"> · :{s.ports.join(", :")}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel p-4" aria-labelledby="dom-h">
          <h2 id="dom-h" className="text-[15px] font-semibold">
            Domenlar va sertifikatlar
          </h2>
          {p.domains_info.length === 0 ? (
            <p className="mt-2 text-muted">Domen biriktirilmagan.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {p.domains_info.map((d) => {
                const dc = certByDomain.get(d.id) ?? [];
                const dp = probesByDomain.get(d.id) ?? [];
                return (
                  <li key={d.id} className="py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="mono font-medium">{d.fqdn}</span>
                      {dc.length > 0 ? (
                        dc.map((c) => <CertBadge key={c.id} daysLeft={c.days_left} />)
                      ) : certs.isPending ? (
                        <span className="text-xs text-muted">sertifikat tekshirilmoqda…</span>
                      ) : (
                        <StatusBadge status="unknown" label="Sertifikat ma'lumoti yo'q" size="sm" />
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted">
                      {dc.map((c) => (
                        <span key={c.id} className="num">
                          tugaydi: {formatDateTime(c.not_after, me.timezone)}
                        </span>
                      ))}
                      {dp.map((pr) => (
                        <StatusBadge key={pr.id} status={effectiveProbeStatus(pr, now)} label={`${PROBE_TYPE[pr.type]}: ${probeLabel(pr, now)}`} size="sm" />
                      ))}
                      {d.status !== "active" && <span>holati: {d.status}</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {certs.error && !certs.data && (
            <div className="mt-3">
              <ErrorState error={certs.error} onRetry={() => void certs.refetch()} title="Sertifikatlarni yuklab bo'lmadi" />
            </div>
          )}
        </section>

        <section className="panel p-4 lg:col-span-2" aria-labelledby="prb-h">
          <h2 id="prb-h" className="mb-2 text-[15px] font-semibold">
            Tekshiruvlar holati
          </h2>
          {probes.isPending ? (
            <SkeletonRows rows={2} className="h-9" />
          ) : probes.error && !probes.data ? (
            <ErrorState error={probes.error} onRetry={() => void probes.refetch()} title="Tekshiruvlarni yuklab bo'lmadi" />
          ) : (
            <ProbesTable probes={probes.data ?? []} now={now} tz={me.timezone} />
          )}
        </section>

        {(p.links.length > 0 || p.notes) && (
          <section className="panel p-4 lg:col-span-2" aria-labelledby="lnk-h">
            <h2 id="lnk-h" className="text-[15px] font-semibold">
              Havolalar va izoh
            </h2>
            {p.links.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                {p.links.map((l, i) => {
                  const href = safeHref(l.url);
                  return (
                    <li key={i}>
                      {href ? (
                        <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                          {l.label || l.url}
                        </a>
                      ) : (
                        <span className="text-muted">{l.label || l.url}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {p.notes && <p className="mt-2 whitespace-pre-wrap">{p.notes}</p>}
          </section>
        )}
      </div>
    </div>
  );
}
