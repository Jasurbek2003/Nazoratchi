import { useId, type ReactNode } from "react";

/** Yorliq + maydon + xato/yordam matni. `children` ga `id` va `aria-*` beriladi. */
export function FormField({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: (props: { id: string; "aria-invalid": boolean; "aria-describedby": string | undefined }) => ReactNode;
}) {
  const id = useId();
  const descId = error || hint ? `${id}-d` : undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-[13px] font-medium">
        {label}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": descId })}
      {error ? (
        <p id={descId} role="alert" className="mt-1 text-[13px] text-critical-fg">
          {error}
        </p>
      ) : hint ? (
        <p id={descId} className="mt-1 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children}
    </div>
  );
}
