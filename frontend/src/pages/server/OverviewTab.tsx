import { useMemo } from "react";
import { useLatest, useUnresolvedIncidents } from "../../api/queries";
import type { Me, ServerDetail } from "../../api/types";
import { IncidentCard } from "../../components/IncidentCard";
import { FreshnessLabel, GaugeBar } from "../../components/Indicators";
import { formatDateTime, formatNumber, formatRate } from "../../lib/format";
import { flattenFacts } from "../../lib/facts";
import { extractVitals, serverDisplayStatus } from "../../lib/serverStatus";
import { hostOf } from "../../lib/summary";
import { useNow } from "../../lib/useNow";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_minmax(0,1fr)] gap-2 py-1.5 sm:grid-cols-[170px_minmax(0,1fr)]">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function OverviewTab({ server, me }: { server: ServerDetail; me: Me }) {
  const now = useNow();
  const latest = useLatest(server.id, server.status === "online" || server.status === "offline");
  const incidents = useUnresolvedIncidents();
  const mine = useMemo(() => (incidents.data ?? []).filter((i) => hostOf(i) === server.id), [incidents.data, server.id]);
  const display = serverDisplayStatus(server, mine, now);
  const vitals = useMemo(() => extractVitals(latest.data, now), [latest.data, now]);
  const facts = useMemo(() => flattenFacts(server.facts), [server.facts]);
  const stale = display.stale;
  const ipLine = [server.public_ipv4, server.public_ipv6].filter(Boolean).join(" · ");

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="panel p-4 lg:col-span-2" aria-labelledby="now-h">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="now-h" className="text-[15px] font-semibold">
            Hozirgi ko&apos;rsatkichlar
          </h2>
          <FreshnessLabel iso={latest.data ? vitals.cpu?.time ?? server.last_seen_at : server.last_seen_at} now={now} tz={me.timezone} prefix="oxirgi ma'lumot: " />
        </div>
        {stale && <p className="mt-2 rounded bg-warning-bg px-3 py-2 text-warning-fg">Server ma&apos;lumot yubormayapti: quyidagi qiymatlar hozirgi emas.</p>}
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4">
          <GaugeBar label="CPU" value={vitals.cpu?.value} stale={stale || !vitals.cpu || vitals.cpu.stale} />
          <GaugeBar label="RAM" value={vitals.mem?.value} stale={stale || !vitals.mem || vitals.mem.stale} />
          <div title={vitals.disk?.detail ? `Eng to'lgan: ${vitals.disk.detail}` : undefined}>
            <GaugeBar label="Disk" value={vitals.disk?.value} stale={stale || !vitals.disk || vitals.disk.stale} />
          </div>
          <div>
            <p className="text-xs text-muted">Yuklama (1 daqiqa)</p>
            <p className={`num text-lg font-semibold ${stale || vitals.load1?.stale ? "text-muted line-through" : ""}`}>{vitals.load1 ? formatNumber(vitals.load1.value, 2) : "—"}</p>
          </div>
        </div>
        <p className="mt-3 text-[13px] text-muted num">
          Tarmoq: kiruvchi {stale ? "—" : formatRate(vitals.rx?.value)} · chiquvchi {stale ? "—" : formatRate(vitals.tx?.value)}
        </p>
      </section>

      <section className="panel p-4 lg:col-span-2" aria-labelledby="inc-h">
        <h2 id="inc-h" className="text-[15px] font-semibold">
          Ochiq incidentlar ({server.open_incidents})
        </h2>
        {incidents.data && mine.length === 0 && server.open_incidents === 0 ? (
          <p className="mt-2 text-muted">Ochiq incident yo&apos;q.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {mine.map((i) => (
              <IncidentCard key={i.id} incident={i} now={now} serverName={server.name} role={me.role} tz={me.timezone} />
            ))}
          </div>
        )}
      </section>

      <section className="panel p-4" aria-labelledby="reg-h">
        <h2 id="reg-h" className="text-[15px] font-semibold">
          Reyestr
        </h2>
        <dl className="mt-2 divide-y divide-line">
          <Field label="Nom">{server.name}</Field>
          <Field label="Manzil">
            <span className="mono">{ipLine || "—"}</span>
          </Field>
          <Field label="Provayder">{server.provider || "—"}</Field>
          <Field label="Joylashuv">{server.location || "—"}</Field>
          <Field label="Rol">{server.role || "—"}</Field>
          <Field label="Teglar">{server.tags.length ? server.tags.join(", ") : "—"}</Field>
          <Field label="Oylik narx">{server.monthly_cost_usd ? `${formatNumber(Number(server.monthly_cost_usd), 2)} USD` : "—"}</Field>
          <Field label="Agent versiyasi">{server.agent_version || "—"}</Field>
          <Field label="Qo'shilgan">{formatDateTime(server.created_at, me.timezone)}</Field>
          <Field label="Izoh">{server.notes || "—"}</Field>
        </dl>
      </section>

      <section className="panel p-4" aria-labelledby="facts-h">
        <h2 id="facts-h" className="text-[15px] font-semibold">
          Faktlar
        </h2>
        {facts.length === 0 ? (
          <p className="mt-2 text-muted">Agent hali fakt yubormagan.</p>
        ) : (
          <dl className="mt-2 divide-y divide-line">
            {facts.map((f) => (
              <Field key={f.key} label={f.label}>
                {f.value}
              </Field>
            ))}
          </dl>
        )}
      </section>
    </div>
  );
}
