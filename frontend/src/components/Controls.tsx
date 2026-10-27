import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { RANGES } from "../api/queries";

/** Tezkor oraliq tugmalari: 1s / 6s / 24s / 7k. Holat URL (`?range=24h`) bilan sinxron — chaqiruvchi boshqaradi. */
export function TimeRangePicker({ value, onChange }: { value: string; onChange: (key: string) => void }) {
  return (
    <div role="group" aria-label="Vaqt oralig'i" className="inline-flex overflow-hidden rounded-md border border-line-strong bg-surface">
      {RANGES.map((r) => {
        const active = r.key === value;
        return (
          <button
            key={r.key}
            type="button"
            aria-pressed={active}
            aria-label={r.aria}
            title={r.aria}
            onClick={() => onChange(r.key)}
            className={`min-h-9 min-w-11 px-3 font-medium num transition-colors max-md:min-h-11 ${
              active ? "bg-accent text-accent-fg" : "text-ink hover:bg-surface-2"
            } border-r border-line-strong last:border-r-0`}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}

export interface TabItem {
  key: string;
  label: string;
  count?: number;
}

/** WAI-ARIA tablar: o'q tugmalari bilan almashadi. Panel tashqarida (`id=panel-<key>`). */
export function Tabs({ items, value, onChange, label }: { items: TabItem[]; value: string; onChange: (key: string) => void; label: string }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % items.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else return;
    e.preventDefault();
    const item = items[next]!;
    onChange(item.key);
    refs.current[item.key]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-line">
      {items.map((t, i) => {
        const active = t.key === value;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[t.key] = el;
            }}
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={active}
            aria-controls={`panel-${t.key}`}
            tabIndex={active ? 0 : -1}
            onKeyDown={(e) => onKey(e, i)}
            onClick={() => onChange(t.key)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3.5 py-2.5 font-medium max-md:min-h-11 ${
              active ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {t.count != null && <span className="ml-1.5 rounded-full bg-surface-2 px-1.5 py-0.5 text-xs num text-muted">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Tasdiqlash dialogi: oqibatni yozadi; Esc bekor qiladi; fokus dialog ichida qoladi va qaytariladi. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Bekor qilish",
  danger,
  busy,
  error,
  confirmDisabled,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const focusables = () => Array.from(el?.querySelectorAll<HTMLElement>("button:not(:disabled), input, select, textarea, [href]") ?? []);
    (focusables().find((f) => f.tagName === "INPUT" || f.tagName === "TEXTAREA") ?? focusables()[0] ?? el)?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCancel();
      } else if (e.key === "Tab") {
        const list = focusables();
        if (list.length === 0) return;
        const first = list[0]!;
        const last = list[list.length - 1]!;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
    // onCancel o'zgarishi fokusni qayta o'rnatmasligi kerak
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-3 sm:items-center" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className="panel w-full max-w-md p-5 shadow-2xl">
        <h2 id={titleId} className="text-base font-semibold">
          {title}
        </h2>
        <div className="mt-2 space-y-3">{children}</div>
        {error && (
          <p role="alert" className="mt-3 rounded bg-critical-bg px-3 py-2 text-critical-fg">
            {error}
          </p>
        )}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm} disabled={busy || confirmDisabled}>
            {busy ? "Bajarilmoqda…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
