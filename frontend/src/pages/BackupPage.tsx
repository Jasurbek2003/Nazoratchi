import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useBackup } from "../api/queries";
import { useCurrentUser, usePageTitle } from "../app/context";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/Feedback";
import { StatusBadge } from "../components/Status";
import { backupState, formatHours } from "../lib/backups";
import { formatBytes, formatDateTime, formatNumber } from "../lib/format";
import { OffsiteBadge } from "./BackupsPage";

function SizeBars({ runs }: { runs: { finished_at: string; size_bytes: number | null }[] }) {
  const max = Math.max(1, ...runs.map((r) => r.size_bytes ?? 0));
  return (
    <div role="img" aria-label={`Oxirgi ${runs.length} ta zaxira hajmi, eng kattasi ${formatBytes(max)}`} className="flex h-24 items-end gap-[3px]">
      {runs.map((r, i) => (
        <span
          key={`${r.finished_at}-${i}`}
          className="min-w-[3px] flex-1 rounded-t-sm bg-accent"
          style={{ height: `${Math.max(4, ((r.size_bytes ?? 0) / max) * 100)}%` }}
          title={`${formatDateTime(r.finished_at)} · ${formatBytes(r.size_bytes)}`}
        />
      ))}
    </div>
  );
}

export default function BackupPage() {
  const { slug = "" } = useParams();
  const me = useCurrentUser();
  const backup = useBackup(slug);
  usePageTitle(backup.data?.name ?? "Zaxira");

  if (backup.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16" label="Zaxira yuklanmoqda" />
        <SkeletonRows rows={2} className="h-24" />
      </div>
    );
  }
  if (backup.error && !backup.data) {
    const notFound = backup.error instanceof ApiError && backup.error.status === 404;
    return notFound ? (
      <EmptyState
        title="Loyiha topilmadi"
        hint="Bu loyiha mavjud emas yoki manzil noto'g'ri."
        action={
          <Link className="btn btn-primary" to="/backups">
            Zaxiralar ro&apos;yxatiga qaytish
          </Link>
        }
      />
    ) : (
      <ErrorState error={backup.error} onRetry={() => void backup.refetch()} title="Zaxirani yuklab bo'lmadi" />
    );
  }

  const b = backup.data!;
  const st = backupState(b.state);
  const runs = b.runs.filter((r) => r.size_bytes != null);
  const policy = [b.expect_daily && "kunlik DB", b.expect_weekly_files && "haftalik fayllar", b.require_offsite && "offsite majburiy"].filter(Boolean).join(", ");

  return (
    <div className="space-y-4">
      <nav aria-label="Joylashuv" className="text-[13px] text-muted">
        <Link to="/backups" className="hover:text-ink hover:underline">
          Zaxiralar
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{b.name}</span>
      </nav>

      <header className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{b.name}</h1>
          <StatusBadge status={st.status} label={st.label} />
        </div>
        <p className="mt-1 text-muted">
          <span className="mono">{b.project}</span>
          {b.server && <> · {b.server}</>} ·{" "}
          <Link className="text-accent hover:underline" to={`/projects/${b.project_id}`}>
            Loyiha sahifasi
          </Link>
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-4" aria-labelledby="bk-sum">
          <h2 id="bk-sum" className="text-[15px] font-semibold">
            Oxirgi zaxira
          </h2>
          <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-muted">Vaqti</dt>
            <dd className="num">{b.last_success_at ? `${formatDateTime(b.last_success_at, me.timezone)} (${formatHours(b.age_hours)} oldin)` : "hech qachon"}</dd>
            <dt className="text-muted">Hajmi</dt>
            <dd className="num">{formatBytes(b.last_size_bytes)}</dd>
            <dt className="text-muted">Natija</dt>
            <dd>{b.last_status === "ok" ? "Muvaffaqiyatli" : b.last_status === "fail" ? "Xato bilan tugagan" : "—"}</dd>
            <dt className="text-muted">Offsite</dt>
            <dd>
              <OffsiteBadge item={b} />
            </dd>
            <dt className="text-muted">Nusxalar</dt>
            <dd className="num">
              kunlik {b.daily_count} · haftalik {b.weekly_count} · fayl {b.files_count}
            </dd>
            <dt className="text-muted">Siyosat</dt>
            <dd>{policy || "belgilanmagan"}</dd>
          </dl>
        </section>

        <section className="panel p-4" aria-labelledby="bk-size">
          <h2 id="bk-size" className="text-[15px] font-semibold">
            Hajm dinamikasi
          </h2>
          {runs.length === 0 ? (
            <p className="mt-2 text-muted">Hali zaxira yozuvi yo&apos;q: grafik birinchi zaxiradan keyin paydo bo&apos;ladi.</p>
          ) : (
            <div className="mt-3 space-y-2">
              <SizeBars runs={runs} />
              {b.size_median_7 != null && (
                <p className="num text-[13px] text-muted">
                  Oxirgi 7 nusxa mediani: {formatBytes(b.size_median_7)}
                  {b.size_ratio != null && ` · oxirgisi ${formatNumber(b.size_ratio, 2)} baravar`}
                </p>
              )}
              {b.size_anomaly && (
                <p role="status" className="rounded bg-warning-bg px-3 py-2 text-warning-fg">
                  Hajm odatdagidan keskin farq qiladi: zaxira to&apos;liq emas yoki ortiqcha ma&apos;lumot qo&apos;shilgan bo&apos;lishi mumkin.
                </p>
              )}
            </div>
          )}
        </section>

        <section className="panel p-4 lg:col-span-2" aria-labelledby="bk-runs">
          <h2 id="bk-runs" className="mb-2 text-[15px] font-semibold">
            Oxirgi zaxiralar ({b.runs.length})
          </h2>
          {b.runs.length === 0 ? (
            <p className="text-muted">Zaxira tarixi bo&apos;sh.</p>
          ) : (
            <div className="max-h-72 overflow-auto">
              <table className="w-full border-collapse text-left">
                <caption className="sr-only">Zaxira ishlari</caption>
                <thead>
                  <tr className="border-b border-line text-[13px] text-muted">
                    <th scope="col" className="py-2 pr-3 font-medium">
                      Tugagan vaqt
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      Hajm
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...b.runs].reverse().map((r, i) => (
                    <tr key={`${r.finished_at}-${i}`} className="border-b border-line last:border-0">
                      <td className="num py-1.5 pr-3">{formatDateTime(r.finished_at, me.timezone)}</td>
                      <td className="num py-1.5">{formatBytes(r.size_bytes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
