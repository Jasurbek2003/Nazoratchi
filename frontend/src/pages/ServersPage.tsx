import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useServers, useUnresolvedIncidents } from "../api/queries";
import type { Incident } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { ServerRow } from "../components/ServerRow";
import { collectTags, filterServers } from "../lib/filters";
import { hostOf } from "../lib/summary";
import { SERVER_STATUS_LABEL } from "../lib/status";

const STATUS_OPTIONS = ["online", "offline", "paused", "new"] as const;

export default function ServersPage() {
  usePageTitle("Serverlar");
  const me = useCurrentUser();
  const [params, setParams] = useSearchParams();
  const servers = useServers();
  const incidents = useUnresolvedIncidents();
  const status = params.get("status") ?? "";
  const tag = params.get("tag") ?? "";
  const q = params.get("q") ?? "";

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const tags = useMemo(() => collectTags(servers.data ?? []), [servers.data]);
  const visible = useMemo(() => filterServers(servers.data ?? [], { status, tag, q }), [servers.data, status, tag, q]);
  const byHost = useMemo(() => {
    const m = new Map<string, Incident[]>();
    for (const i of incidents.data ?? []) {
      const h = hostOf(i);
      if (h) m.set(h, [...(m.get(h) ?? []), i]);
    }
    return m;
  }, [incidents.data]);
  const filtered = !!(status || tag || q);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Serverlar</h1>
        <p className="text-muted num" aria-live="polite">
          {servers.data ? `${visible.length} / ${servers.data.length} server` : ""}
        </p>
      </div>

      <form role="search" aria-label="Serverlarni filtrlash" className="grid gap-2 sm:grid-cols-[minmax(0,2fr)_repeat(2,minmax(0,1fr))_auto]" onSubmit={(e) => e.preventDefault()}>
        <div>
          <label htmlFor="srv-q" className="sr-only">
            Qidirish
          </label>
          <input id="srv-q" type="search" className="field" placeholder="Nom, IP, provayder yoki teg bo'yicha qidirish" value={q} onChange={(e) => set("q", e.target.value)} />
        </div>
        <div>
          <label htmlFor="srv-status" className="sr-only">
            Holat
          </label>
          <select id="srv-status" className="field" value={status} onChange={(e) => set("status", e.target.value)}>
            <option value="">Barcha holatlar</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {SERVER_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="srv-tag" className="sr-only">
            Teg
          </label>
          <select id="srv-tag" className="field" value={tag} onChange={(e) => set("tag", e.target.value)} disabled={tags.length === 0}>
            <option value="">Barcha teglar</option>
            {tags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn" disabled={!filtered} onClick={() => setParams({}, { replace: true })}>
          Tozalash
        </button>
      </form>

      {servers.isPending ? (
        <SkeletonRows rows={5} className="h-[76px]" />
      ) : servers.error && !servers.data ? (
        <ErrorState error={servers.error} onRetry={() => void servers.refetch()} title="Serverlarni yuklab bo'lmadi" />
      ) : servers.data!.length === 0 ? (
        <EmptyState title="Hali server ulanmagan" hint="Agent ulangan serverlar shu yerda ko'rinadi." />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Hech narsa topilmadi"
          hint="Filtr yoki qidiruv shartlariga mos server yo'q."
          action={
            <button type="button" className="btn" onClick={() => setParams({}, { replace: true })}>
              Filtrni tozalash
            </button>
          }
        />
      ) : (
        <ul className="m-0 list-none space-y-2 p-0">
          {visible.map((s) => (
            <ServerRow key={s.id} server={s} incidents={byHost.get(s.id) ?? []} tz={me.timezone} />
          ))}
        </ul>
      )}
    </div>
  );
}
