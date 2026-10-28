import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useCerts, useDomain, useDomainDns, useProbes } from "../api/queries";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/Feedback";
import { CertBadge } from "../components/Indicators";
import { StatusBadge } from "../components/Status";
import { answerList } from "../lib/backups";
import { ipList, probeBadge } from "../lib/domains";
import { formatAgoFrom, formatDateTime, formatNumber } from "../lib/format";
import { useNow } from "../lib/useNow";

const PROBE_TYPE: Record<string, string> = { http: "HTTP", tcp: "TCP", tls: "TLS", dns: "DNS", whois: "WHOIS" };

function Answers({ value }: { value: unknown }) {
  const list = answerList(value);
  if (list.length === 0) return <span className="text-muted">javob yo&apos;q</span>;
  return <span className="mono break-all">{list.join(", ")}</span>;
}

export default function DomainPage() {
  const { id = "" } = useParams();
  const me = useCurrentUser();
  const now = useNow();
  const domain = useDomain(id);
  const dns = useDomainDns(id);
  const probes = useProbes();
  const certs = useCerts();
  usePageTitle(domain.data?.fqdn ?? "Domen");

  const myProbes = useMemo(() => (probes.data ?? []).filter((p) => p.domain === id), [probes.data, id]);
  const myCerts = useMemo(() => (certs.data ?? []).filter((c) => c.domain === id), [certs.data, id]);

  if (domain.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16" label="Domen yuklanmoqda" />
        <SkeletonRows rows={2} className="h-24" />
      </div>
    );
  }
  if (domain.error && !domain.data) {
    const notFound = domain.error instanceof ApiError && domain.error.status === 404;
    return notFound ? (
      <EmptyState
        title="Domen topilmadi"
        hint="Bu domen mavjud emas yoki manzil noto'g'ri."
        action={
          <Link className="btn btn-primary" to="/domains">
            Domenlar ro&apos;yxatiga qaytish
          </Link>
        }
      />
    ) : (
      <ErrorState error={domain.error} onRetry={() => void domain.refetch()} title="Domenni yuklab bo'lmadi" />
    );
  }

  const d = domain.data!;
  const expected = ipList(d.expected_ips);

  return (
    <div className="space-y-4">
      <nav aria-label="Joylashuv" className="text-[13px] text-muted">
        <Link to="/domains" className="hover:text-ink hover:underline">
          Domenlar
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{d.fqdn}</span>
      </nav>

      <header className="panel p-4">
        <h1 className="mono break-all text-2xl font-semibold tracking-tight">{d.fqdn}</h1>
        <p className="mt-1 flex flex-wrap gap-x-3 text-muted">
          <span>DNS provayder: {d.dns_provider || "aniqlanmagan"}</span>
          <span>nazorat: {d.controlled_by || "—"}</span>
          {d.registrar && <span>registrator: {d.registrar}</span>}
          {d.project && d.project_slug && (
            <Link className="text-accent hover:underline" to={`/projects/${d.project}`}>
              Loyiha: {d.project_slug}
            </Link>
          )}
        </p>
        {d.notes && <p className="mt-2 max-w-3xl">{d.notes}</p>}
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-4 lg:col-span-2" aria-labelledby="dns-h">
          <h2 id="dns-h" className="text-[15px] font-semibold">
            DNS holati
          </h2>
          <p className="mt-1 text-muted">
            Kutilgan IP: {expected.length ? <span className="mono">{expected.join(", ")}</span> : "belgilanmagan"}
          </p>
          {dns.isPending ? (
            <div className="mt-2">
              <SkeletonRows rows={3} className="h-8" />
            </div>
          ) : dns.error && !dns.data ? (
            <div className="mt-2">
              <ErrorState error={dns.error} onRetry={() => void dns.refetch()} title="DNS ma'lumotini yuklab bo'lmadi" />
            </div>
          ) : dns.data!.resolvers.length === 0 ? (
            <p className="mt-2 text-muted">Hali DNS tekshiruvi natijasi yo&apos;q. Birinchi tekshiruv bajarilgach shu yerda ko&apos;rinadi.</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[520px] border-collapse text-left">
                <caption className="sr-only">Resolverlar bo&apos;yicha DNS javoblari</caption>
                <thead>
                  <tr className="border-b border-line text-[13px] text-muted">
                    <th scope="col" className="py-2 pr-3 font-medium">Resolver</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Javob</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Holat</th>
                    <th scope="col" className="py-2 font-medium">Tekshirilgan</th>
                  </tr>
                </thead>
                <tbody>
                  {dns.data!.resolvers.map((r) => (
                    <tr key={`${r.resolver}-${r.rtype}`} className="border-b border-line last:border-0">
                      <th scope="row" className="py-2 pr-3 font-medium">
                        {r.resolver} <span className="text-xs text-muted">{r.rtype}</span>
                      </th>
                      <td className="py-2 pr-3">
                        <Answers value={r.answers} />
                      </td>
                      <td className="py-2 pr-3">
                        <StatusBadge status={r.matches == null ? "unknown" : r.matches ? "ok" : "critical"} label={r.matches == null ? "Noma'lum" : r.matches ? "Mos" : "Mos emas"} size="sm" />
                      </td>
                      <td className="num py-2 text-muted" title={formatDateTime(r.time, me.timezone)}>
                        {formatAgoFrom(r.time, now)}
                        {r.latency_ms != null && ` · ${formatNumber(r.latency_ms, 0)} ms`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel p-4" aria-labelledby="crt-h">
          <h2 id="crt-h" className="text-[15px] font-semibold">
            Sertifikatlar
          </h2>
          {certs.error && !certs.data ? (
            <div className="mt-2">
              <ErrorState error={certs.error} onRetry={() => void certs.refetch()} title="Sertifikatlarni yuklab bo'lmadi" />
            </div>
          ) : certs.isPending ? (
            <div className="mt-2">
              <SkeletonRows rows={1} className="h-9" />
            </div>
          ) : myCerts.length === 0 ? (
            <p className="mt-2 text-muted">{d.tls_enabled ? "Sertifikat ma'lumoti hali yo'q." : "Bu domen uchun TLS kutilmaydi."}</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {myCerts.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    {c.name}
                    <span className="block text-xs text-muted num">tugaydi: {formatDateTime(c.not_after, me.timezone)}</span>
                  </span>
                  <CertBadge daysLeft={c.days_left} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel p-4" aria-labelledby="prb-h">
          <h2 id="prb-h" className="text-[15px] font-semibold">
            Tekshiruvlar
          </h2>
          {probes.error && !probes.data ? (
            <div className="mt-2">
              <ErrorState error={probes.error} onRetry={() => void probes.refetch()} title="Tekshiruvlarni yuklab bo'lmadi" />
            </div>
          ) : probes.isPending ? (
            <div className="mt-2">
              <SkeletonRows rows={1} className="h-9" />
            </div>
          ) : myProbes.length === 0 ? (
            <p className="mt-2 text-muted">Bu domen uchun tekshiruv sozlanmagan.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {myProbes.map((p) => {
                const b = probeBadge(p, now);
                return (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span>
                      {p.name}
                      <span className="ml-2 text-xs text-muted">{PROBE_TYPE[p.type] ?? p.type}</span>
                    </span>
                    <StatusBadge status={b.status} label={b.label} size="sm" />
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="panel p-4 lg:col-span-2" aria-labelledby="chg-h">
          <h2 id="chg-h" className="text-[15px] font-semibold">
            DNS o&apos;zgarishlari
          </h2>
          {dns.data && dns.data.changes.length === 0 ? (
            <p className="mt-2 text-muted">O&apos;zgarish qayd etilmagan.</p>
          ) : dns.data ? (
            <ol className="mt-2 space-y-1.5">
              {dns.data.changes.map((c, i) => (
                <li key={`${c.changed_at}-${i}`} className="flex flex-wrap gap-x-2">
                  <time className="num text-muted" dateTime={c.changed_at}>
                    {formatDateTime(c.changed_at, me.timezone)}
                  </time>
                  <span>
                    {c.resolver} {c.rtype}: <Answers value={c.old_answers} /> → <Answers value={c.new_answers} />
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-muted">Ma&apos;lumot yuklanmadi.</p>
          )}
        </section>

        <section className="panel p-4 lg:col-span-2" aria-labelledby="cut-h">
          <h2 id="cut-h" className="text-[15px] font-semibold">
            Kesib o&apos;tish yordamchisi
          </h2>
          <p className="mt-2 text-muted">
            Oldindan tekshirish va tarqalishni kuzatish hozircha mavjud emas (server tomoni keyingi bosqichda). Hozir DNS holati va o&apos;zgarishlarni yuqoridan kuzating.
          </p>
        </section>
      </div>
    </div>
  );
}
