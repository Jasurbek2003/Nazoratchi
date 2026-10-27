import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { RANGES, useContainers, useFilesystems, useServer, useUnresolvedIncidents } from "../api/queries";
import { useCurrentUser, usePageTitle } from "../app/context";
import { Tabs, TimeRangePicker, type TabItem } from "../components/Controls";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { FreshnessLabel } from "../components/Indicators";
import { StatusBadge } from "../components/Status";
import { formatAgoFrom, formatDateTime } from "../lib/format";
import { serverDisplayStatus } from "../lib/serverStatus";
import { hostOf } from "../lib/summary";
import { useNow } from "../lib/useNow";
import { ContainersTab } from "./server/ContainersTab";
import { FilesystemsTab } from "./server/FilesystemsTab";
import { OverviewTab } from "./server/OverviewTab";
import { PauseControls } from "./server/PauseControls";
import { ResourcesTab } from "./server/ResourcesTab";

const TAB_KEYS = ["overview", "resources", "containers", "filesystems"] as const;
type TabKey = (typeof TAB_KEYS)[number];

export default function ServerPage() {
  const { id = "" } = useParams();
  const me = useCurrentUser();
  const now = useNow();
  const [params, setParams] = useSearchParams();
  const server = useServer(id);
  const incidents = useUnresolvedIncidents();
  const containers = useContainers(id);
  const filesystems = useFilesystems(id);
  usePageTitle(server.data?.name ?? "Server");

  const tab: TabKey = (TAB_KEYS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as TabKey) : "overview";
  const range = RANGES.some((r) => r.key === params.get("range")) ? params.get("range")! : "6h";
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  };

  const mine = useMemo(() => (incidents.data ?? []).filter((i) => hostOf(i) === id), [incidents.data, id]);

  if (server.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16" label="Server yuklanmoqda" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (server.error && !server.data) {
    const notFound = server.error instanceof ApiError && server.error.status === 404;
    return notFound ? (
      <EmptyState
        title="Server topilmadi"
        hint="Bu server o'chirilgan yoki manzil noto'g'ri."
        action={
          <Link className="btn btn-primary" to="/servers">
            Serverlar ro&apos;yxatiga qaytish
          </Link>
        }
      />
    ) : (
      <ErrorState error={server.error} onRetry={() => void server.refetch()} title="Serverni yuklab bo'lmadi" />
    );
  }

  const s = server.data!;
  const display = serverDisplayStatus(s, mine, now);
  const tabs: TabItem[] = [
    { key: "overview", label: "Umumiy" },
    { key: "resources", label: "Resurslar" },
    { key: "containers", label: "Konteynerlar", count: containers.data?.length },
    { key: "filesystems", label: "Fayl tizimlari", count: filesystems.data?.length },
  ];

  return (
    <div className="space-y-4">
      <nav aria-label="Joylashuv" className="text-[13px] text-muted">
        <Link to="/servers" className="hover:text-ink hover:underline">
          Serverlar
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{s.name}</span>
      </nav>

      <header className="panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight">{s.name}</h1>
              <StatusBadge status={display.status} label={display.label} />
            </div>
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-muted">
              <span className="mono">{s.public_ipv4 ?? s.public_ipv6 ?? "IP yo'q"}</span>
              {s.provider && <span>{s.provider}</span>}
              {s.agent_version && <span>agent {s.agent_version}</span>}
              <FreshnessLabel iso={s.last_seen_at} now={now} tz={me.timezone} prefix="oxirgi aloqa: " />
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PauseControls server={s} role={me.role} />
          </div>
        </div>
        {s.status === "paused" && (
          <div className="mt-3 rounded-md border border-dashed border-unknown bg-unknown-bg px-3 py-2 text-unknown-fg">
            <p>
              <span className="font-semibold">Pauzada:</span> {s.pause_reason || "sabab ko'rsatilmagan"}
            </p>
            <p className="text-[13px]">
              {s.paused_until ? `Avtomatik davom etadi: ${formatDateTime(s.paused_until, me.timezone)}` : "Muddatsiz — qo'lda davom ettiriladi"}
              {s.paused_at ? ` · boshlangan: ${formatAgoFrom(s.paused_at, now)}` : ""}
            </p>
          </div>
        )}
        {s.status === "new" && <p className="mt-3 text-muted">Birinchi ma&apos;lumot kutilmoqda. Agent ulangach, ko&apos;rsatkichlar shu yerda paydo bo&apos;ladi.</p>}
      </header>

      <Tabs items={tabs} value={tab} onChange={(k) => update("tab", k)} label="Server bo'limlari" />

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0} className="outline-none">
        {tab === "overview" && <OverviewTab server={s} me={me} />}
        {tab === "resources" && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <TimeRangePicker value={range} onChange={(k) => update("range", k)} />
              <p className="text-[13px] text-muted">Vaqt zonasi: {me.timezone}</p>
            </div>
            <ResourcesTab serverId={s.id} range={range} tz={me.timezone} />
          </div>
        )}
        {tab === "containers" && <ContainersTab serverId={s.id} />}
        {tab === "filesystems" && <FilesystemsTab serverId={s.id} />}
      </div>
    </div>
  );
}
