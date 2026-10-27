import { useState, type ReactNode } from "react";
import { ApiError } from "../api/client";

export function Skeleton({ className = "", label }: { className?: string; label?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden={label ? undefined : true} aria-label={label} role={label ? "status" : undefined} />;
}

export function SkeletonRows({ rows = 4, className = "h-14" }: { rows?: number; className?: string }) {
  return (
    <div className="space-y-2" role="status" aria-label="Yuklanmoqda">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={className} />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="panel flex flex-col items-center gap-2 px-6 py-10 text-center">
      <p className="text-[15px] font-semibold">{title}</p>
      {hint && <p className="max-w-md text-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function describeError(error: unknown): { message: string; requestId: string | null; status: number | null } {
  if (error instanceof ApiError) {
    if (error.status === 403) return { message: "Bu bo'limni ko'rish uchun ruxsat yo'q.", requestId: error.requestId, status: 403 };
    return { message: error.message, requestId: error.requestId, status: error.status };
  }
  if (error instanceof TypeError) return { message: "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.", requestId: null, status: null };
  return { message: "Kutilmagan xato yuz berdi.", requestId: null, status: null };
}

/** API xatosi: qisqa xabar + "Qayta urinish" + `request_id` (nusxalash) — TZ 13.12. */
export function ErrorState({ error, onRetry, title = "Ma'lumotni yuklab bo'lmadi" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const info = describeError(error);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (!info.requestId) return;
    try {
      await navigator.clipboard.writeText(info.requestId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard ruxsati yo'q */
    }
  };
  return (
    <div role="alert" className="panel border-critical/50 bg-critical-bg px-4 py-4">
      <p className="font-semibold text-critical-fg">{title}</p>
      <p className="mt-1 text-ink">{info.message}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            Qayta urinish
          </button>
        )}
        {info.requestId && (
          <button type="button" className="btn" onClick={copy} aria-label={`So'rov identifikatorini nusxalash: ${info.requestId}`}>
            {copied ? "Nusxalandi" : `So'rov ID: ${info.requestId.slice(0, 8)}`}
          </button>
        )}
      </div>
    </div>
  );
}
