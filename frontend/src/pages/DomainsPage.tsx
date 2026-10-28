import { memo, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCerts, useDomains, useProbes } from "../api/queries";
import { usePageTitle } from "../app/context";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { PageHeader } from "../components/FormField";
import { CertBadge } from "../components/Indicators";
import { StatusBadge } from "../components/Status";
import { buildDomainRows, certExpiring, dnsProblem, probeBadge, type DomainRowData } from "../lib/domains";
import { formatNumber } from "../lib/format";
import { useNow } from "../lib/useNow";

const COLS = "md:grid-cols-[minmax(170px,1.5fr)_minmax(110px,1fr)_130px_130px_130px]";

const Row = memo(function Row({ row, now }: { row: DomainRowData; now: number }) {
  const http = probeBadge(row.http, now);
  const dns = probeBadge(row.dns, now);
  const code = row.http?.last_result?.status_code;
  return (
    <li data-testid="domain-row" className={`panel relative grid grid-cols-2 items-start gap-x-4 gap-y-2 px-4 py-3 hover:bg-surface-2 ${COLS}`}>
      <div className="col-span-2 min-w-0 md:col-span-1">
        <Link to={`/domains/${row.domain.id}`} className="mono break-all font-semibold after:absolute after:inset-0 after:content-['']">
          {row.domain.fqdn}
        </Link>
        {row.domain.status !== "active" && <p className="text-xs text-muted">holati: {row.domain.status}</p>}
      </div>
      <div className="min-w-0 truncate">
        <p className="text-xs text-muted md:sr-only">Loyiha</p>
        {row.domain.project_slug ?? <span className="text-muted">biriktirilmagan</span>}
      </div>
      <div>
        <p className="text-xs text-muted md:sr-only">HTTP</p>
        <StatusBadge status={http.status} label={code ? `${http.label} · ${formatNumber(code, 0)}` : http.label} size="sm" />
      </div>
      <div>
        <p className="text-xs text-muted md:sr-only">Sertifikat</p>
        {row.minDaysLeft != null ? <CertBadge daysLeft={row.minDaysLeft} /> : <StatusBadge status="unknown" label={row.domain.tls_enabled ? "Ma'lumot yo'q" : "TLS kutilmaydi"} size="sm" />}
      </div>
      <div>
        <p className="text-xs text-muted md:sr-only">DNS</p>
        <StatusBadge status={dns.status} label={dns.label} size="sm" />
      </div>
    </li>
  );
});

export default function DomainsPage() {
  usePageTitle("Domenlar");
  const now = Math.floor(useNow() / 15_000) * 15_000;
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const expiring = params.get("expiring") === "1";
  const dnsOnly = params.get("dns") === "1";
  const domains = useDomains();
  const probes = useProbes();
  const certs = useCerts();

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const rows = useMemo(() => buildDomainRows(domains.data ?? [], probes.data ?? [], certs.data ?? []), [domains.data, probes.data, certs.data]);
  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (!needle || r.domain.fqdn.includes(needle) || (r.domain.project_slug ?? "").toLowerCase().includes(needle)) &&
        (!expiring || certExpiring(r)) &&
        (!dnsOnly || dnsProblem(r, now)),
    );
  }, [rows, q, expiring, dnsOnly, now]);
  const filtered = q !== "" || expiring || dnsOnly;

  const partial = (probes.error && !probes.data) || (certs.error && !certs.data);

  return (
    <div className="space-y-4">
      <PageHeader title="Domenlar">
        <p className="text-muted num" aria-live="polite">
          {domains.data ? `${visible.length} / ${domains.data.length} domen` : ""}
        </p>
      </PageHeader>

      <form role="search" aria-label="Domenlarni filtrlash" className="flex flex-wrap items-center gap-x-4 gap-y-2" onSubmit={(e) => e.preventDefault()}>
        <div className="min-w-[200px] flex-1">
          <label htmlFor="dom-q" className="sr-only">
            Qidirish
          </label>
          <input id="dom-q" type="search" className="field" placeholder="Domen yoki loyiha bo'yicha qidirish" value={q} onChange={(e) => set("q", e.target.value)} />
        </div>
        <label className="inline-flex items-center gap-2 max-md:min-h-11">
          <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={expiring} onChange={(e) => set("expiring", e.target.checked ? "1" : "")} />
          Muddati yaqin
        </label>
        <label className="inline-flex items-center gap-2 max-md:min-h-11">
          <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={dnsOnly} onChange={(e) => set("dns", e.target.checked ? "1" : "")} />
          DNS muammolari
        </label>
      </form>

      {partial && (
        <p role="status" className="rounded bg-warning-bg px-3 py-2 text-warning-fg">
          Tekshiruv yoki sertifikat ma&apos;lumoti yuklanmadi: tegishli ustunlarda &quot;noma&apos;lum&quot; ko&apos;rsatiladi.
        </p>
      )}

      {domains.isPending ? (
        <SkeletonRows rows={5} className="h-[72px]" />
      ) : domains.error && !domains.data ? (
        <ErrorState error={domains.error} onRetry={() => void domains.refetch()} title="Domenlarni yuklab bo'lmadi" />
      ) : domains.data!.length === 0 ? (
        <EmptyState title="Hali domen qo'shilmagan" hint="Loyihaga domen biriktirilgach, uning HTTP, sertifikat va DNS holati shu yerda ko'rinadi." />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Hech narsa topilmadi"
          hint="Filtr shartiga mos domen yo'q."
          action={
            filtered ? (
              <button type="button" className="btn" onClick={() => setParams({}, { replace: true })}>
                Filtrni tozalash
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className={`hidden px-4 text-xs font-medium text-muted md:grid md:gap-x-4 ${COLS}`} aria-hidden>
            <span>Domen</span>
            <span>Loyiha</span>
            <span>HTTP</span>
            <span>Sertifikat</span>
            <span>DNS</span>
          </div>
          <ul className="m-0 list-none space-y-2 p-0">
            {visible.map((r) => (
              <Row key={r.domain.id} row={r} now={now} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
