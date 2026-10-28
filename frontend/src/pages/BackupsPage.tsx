import { memo, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useBackups } from "../api/queries";
import type { BackupItem } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { PageHeader } from "../components/FormField";
import { StatusBadge, STATUS_CLASS } from "../components/Status";
import { backupState, formatHours } from "../lib/backups";
import { formatBytes, formatDateTime } from "../lib/format";

const COLS = "md:grid-cols-[minmax(150px,1.4fr)_minmax(90px,1fr)_110px_90px_130px_150px]";

export function OffsiteBadge({ item }: { item: Pick<BackupItem, "offsite_configured" | "require_offsite"> }) {
  if (item.offsite_configured == null) return <span className="text-muted">—</span>;
  if (item.offsite_configured) return <StatusBadge status="ok" label="Sozlangan" size="sm" />;
  return <StatusBadge status={item.require_offsite ? "warning" : "unknown"} label="Sozlanmagan" size="sm" />;
}

const Row = memo(function Row({ item, tz }: { item: BackupItem; tz: string }) {
  const st = backupState(item.state);
  return (
    <li data-testid="backup-row" className={`panel relative grid grid-cols-2 items-start gap-x-4 gap-y-2 py-3 pl-4 pr-3 hover:bg-surface-2 ${COLS}`}>
      <span className={`absolute inset-y-0 left-0 w-1 rounded-l-[10px] ${STATUS_CLASS[st.status].bar}`} aria-hidden />
      <div className="col-span-2 min-w-0 md:col-span-1">
        <Link to={`/backups/${encodeURIComponent(item.project)}`} className="font-semibold after:absolute after:inset-0 after:content-['']">
          {item.name}
        </Link>
        <p className="mono truncate text-xs text-muted">{item.project}</p>
      </div>
      <div className="min-w-0 truncate">
        <p className="text-xs text-muted md:sr-only">Server</p>
        {item.server ?? <span className="text-muted">—</span>}
      </div>
      <div className="num" title={item.last_success_at ? formatDateTime(item.last_success_at, tz) : undefined}>
        <p className="text-xs text-muted md:sr-only">Oxirgisi</p>
        {item.age_hours == null ? <span className="text-muted">hech qachon</span> : `${formatHours(item.age_hours)} oldin`}
      </div>
      <div className="num">
        <p className="text-xs text-muted md:sr-only">Hajm</p>
        {formatBytes(item.last_size_bytes)}
      </div>
      <div>
        <p className="text-xs text-muted md:sr-only">Offsite</p>
        <OffsiteBadge item={item} />
      </div>
      <div>
        <StatusBadge status={st.status} label={st.label} size="sm" />
      </div>
    </li>
  );
});

export default function BackupsPage() {
  usePageTitle("Zaxiralar");
  const me = useCurrentUser();
  const [params, setParams] = useSearchParams();
  const onlyProblems = params.get("problems") === "1";
  const backups = useBackups();

  const visible = useMemo(() => {
    const list = backups.data ?? [];
    return onlyProblems ? list.filter((b) => backupState(b.state).problem) : list;
  }, [backups.data, onlyProblems]);

  const setProblems = (on: boolean) => {
    const next = new URLSearchParams(params);
    if (on) next.set("problems", "1");
    else next.delete("problems");
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Zaxiralar">
        <label className="inline-flex items-center gap-2 max-md:min-h-11">
          <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={onlyProblems} onChange={(e) => setProblems(e.target.checked)} />
          Faqat muammolilar
        </label>
      </PageHeader>

      {backups.isPending ? (
        <SkeletonRows rows={5} className="h-[72px]" />
      ) : backups.error && !backups.data ? (
        <ErrorState error={backups.error} onRetry={() => void backups.refetch()} title="Zaxiralarni yuklab bo'lmadi" />
      ) : backups.data!.length === 0 ? (
        <EmptyState title="Zaxira kuzatuvi sozlanmagan" hint="Loyihaga zaxira siyosatini belgilang yoki agent zaxira ma'lumotini yuborishini kuting." />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Muammoli zaxira yo'q"
          hint="Kuzatilayotgan hamma zaxira joyida."
          action={
            <button type="button" className="btn" onClick={() => setProblems(false)}>
              Hammasini ko&apos;rsatish
            </button>
          }
        />
      ) : (
        <>
          <div className={`hidden px-4 text-xs font-medium text-muted md:grid md:gap-x-4 ${COLS}`} aria-hidden>
            <span>Loyiha</span>
            <span>Server</span>
            <span>Oxirgisi</span>
            <span>Hajm</span>
            <span>Offsite</span>
            <span>Holat</span>
          </div>
          <ul className="m-0 list-none space-y-2 p-0">
            {visible.map((b) => (
              <Row key={b.project_id} item={b} tz={me.timezone} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
