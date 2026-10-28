import { useMemo, useState } from "react";
import { useController, useFieldArray, useForm, type Control } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useCancelMaintenance, useCancelSilence, useCreateMaintenance, useCreateSilence, useMaintenance, useProjects, useServers, useSilences } from "../api/queries";
import type { MaintenanceWindow, Silence } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { ConfirmDialog, Tabs } from "../components/Controls";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { FormField, PageHeader } from "../components/FormField";
import { StatusBadge } from "../components/Status";
import { formatDateTime } from "../lib/format";
import {
  describeMatcher,
  DURATIONS,
  maintenanceSchema,
  MATCHER_LABELS,
  MATCHER_OPS,
  silenceEndsAt,
  silenceSchema,
  toLocalInput,
  windowPhase,
  type MaintenanceForm,
  type SilenceForm,
} from "../lib/suppression";
import { useNow } from "../lib/useNow";

function submitMessage(e: unknown): string {
  if (e instanceof ApiError) return e.status === 403 ? "Bu amal uchun ruxsat yo'q." : e.message;
  return "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.";
}

// ------------------------------------------------------------------ silence
function SilenceFormPanel({ onDone }: { onDone: () => void }) {
  const create = useCreateSilence();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    control,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<SilenceForm>({
    resolver: zodResolver(silenceSchema),
    defaultValues: { matchers: [{ label: "server", op: "=", value: "" }], duration: "4h", custom_ends: "", reason: "" },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "matchers" });
  const duration = watch("duration");

  const onSubmit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({ matchers: v.matchers, ends_at: silenceEndsAt(v), reason: v.reason });
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        for (const d of e.details) {
          if (d.field === "reason") setError("reason", { message: d.message });
        }
      }
      setFormError(submitMessage(e));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Yangi silence" className="panel space-y-4 p-4">
      <h2 className="text-[15px] font-semibold">Yangi silence</h2>
      <p className="text-muted">Shartlarga mos alertlar bildirishnoma yubormaydi (incident baribir yoziladi).</p>
      <fieldset className="space-y-2">
        <legend className="mb-1 text-[13px] font-medium">Shartlar (hammasi bajarilishi kerak)</legend>
        {fields.map((f, i) => (
          <div key={f.id} className="grid gap-2 sm:grid-cols-[150px_150px_minmax(0,1fr)_auto]">
            <div>
              <label htmlFor={`m-label-${i}`} className="sr-only">
                {i + 1}-shart: maydon
              </label>
              <select id={`m-label-${i}`} className="field" {...register(`matchers.${i}.label`)}>
                {MATCHER_LABELS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`m-op-${i}`} className="sr-only">
                {i + 1}-shart: amal
              </label>
              <select id={`m-op-${i}`} className="field" {...register(`matchers.${i}.op`)}>
                {MATCHER_OPS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`m-val-${i}`} className="sr-only">
                {i + 1}-shart: qiymat
              </label>
              <input id={`m-val-${i}`} className="field" placeholder="Masalan: main-2" aria-invalid={Boolean(errors.matchers?.[i]?.value)} {...register(`matchers.${i}.value`)} />
              {errors.matchers?.[i]?.value && (
                <p role="alert" className="mt-1 text-[13px] text-critical-fg">
                  {errors.matchers[i]!.value!.message}
                </p>
              )}
            </div>
            <button type="button" className="btn" disabled={fields.length === 1} onClick={() => remove(i)} aria-label={`${i + 1}-shartni olib tashlash`}>
              Olib tashlash
            </button>
          </div>
        ))}
        {errors.matchers?.message && (
          <p role="alert" className="text-[13px] text-critical-fg">
            {errors.matchers.message}
          </p>
        )}
        <button type="button" className="btn" disabled={fields.length >= 10} onClick={() => append({ label: "server", op: "=", value: "" })}>
          Shart qo&apos;shish
        </button>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <FormField label="Muddat">
          {(p) => (
            <select className="field" {...p} {...register("duration")}>
              {DURATIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          )}
        </FormField>
        {duration === "custom" && (
          <FormField label="Tugash vaqti" error={errors.custom_ends?.message} hint="Kamida 15 daqiqa, ko'pi bilan 30 kun.">
            {(p) => <input type="datetime-local" className="field" {...p} {...register("custom_ends")} />}
          </FormField>
        )}
      </div>

      <FormField label="Sabab" error={errors.reason?.message}>
        {(p) => <input className="field" maxLength={300} placeholder="Masalan: rejali yangilash" {...p} {...register("reason")} />}
      </FormField>

      {formError && (
        <p role="alert" className="rounded bg-critical-bg px-3 py-2 text-critical-fg">
          {formError}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Saqlanmoqda…" : "Saqlash"}
        </button>
        <button type="button" className="btn" onClick={onDone}>
          Bekor qilish
        </button>
      </div>
    </form>
  );
}

function SilencesTab({ canWrite, tz }: { canWrite: boolean; tz: string }) {
  const silences = useSilences();
  const cancel = useCancelSilence();
  const [creating, setCreating] = useState(false);
  const [target, setTarget] = useState<Silence | null>(null);

  return (
    <div className="space-y-3">
      {canWrite && !creating && (
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          Yangi silence
        </button>
      )}
      {creating && <SilenceFormPanel onDone={() => setCreating(false)} />}

      {silences.isPending ? (
        <SkeletonRows rows={3} className="h-16" />
      ) : silences.error && !silences.data ? (
        <ErrorState error={silences.error} onRetry={() => void silences.refetch()} title="Silence ro'yxatini yuklab bo'lmadi" />
      ) : silences.data!.length === 0 ? (
        <EmptyState title="Faol silence yo'q" hint="Vaqtinchalik shovqinni o'chirish kerak bo'lsa, silence yarating." />
      ) : (
        <ul className="m-0 list-none space-y-2 p-0">
          {silences.data!.map((s) => (
            <li key={s.id} data-testid="silence-row" className="panel flex flex-wrap items-start justify-between gap-3 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{s.matchers.map(describeMatcher).join(" va ")}</p>
                <p className="text-muted">{s.reason}</p>
                <p className="num text-[13px] text-muted">
                  Tugaydi: {formatDateTime(s.ends_at, tz)}
                  {s.created_by && ` · ${s.created_by}`}
                </p>
              </div>
              {canWrite && (
                <button type="button" className="btn" onClick={() => setTarget(s)}>
                  Bekor qilish
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={target != null}
        title="Silence bekor qilinadimi?"
        confirmLabel="Bekor qilish"
        cancelLabel="Qoldirish"
        danger
        busy={cancel.isPending}
        error={cancel.isError ? submitMessage(cancel.error) : null}
        onCancel={() => setTarget(null)}
        onConfirm={() => target && cancel.mutate(target.id, { onSuccess: () => setTarget(null) })}
      >
        <p>Mos alertlar uchun bildirishnomalar darhol qayta yoqiladi.</p>
      </ConfirmDialog>
    </div>
  );
}

// ------------------------------------------------------------------ texnik ish
/** Belgilanganlar massivi (RHF ning yagona-checkbox xususiyatidan qochish uchun boshqariladigan). */
function CheckList({ control, name, options }: { control: Control<MaintenanceForm>; name: "servers" | "projects"; options: { value: string; label: string }[] }) {
  const { field } = useController({ control, name });
  const value = field.value;
  if (options.length === 0) return <p className="text-muted">Ro&apos;yxat bo&apos;sh.</p>;
  return (
    <div className="max-h-44 space-y-1 overflow-auto">
      {options.map((o) => (
        <label key={o.value} className="flex items-center gap-2 max-md:min-h-11">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--accent)]"
            checked={value.includes(o.value)}
            onChange={(e) => field.onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function MaintenanceFormPanel({ onDone }: { onDone: () => void }) {
  const create = useCreateMaintenance();
  const servers = useServers();
  const projects = useProjects("active");
  const [formError, setFormError] = useState<string | null>(null);
  const defaults = useMemo(() => {
    const start = new Date();
    return { start: toLocalInput(start), end: toLocalInput(new Date(start.getTime() + 2 * 3600_000)) };
  }, []);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<MaintenanceForm>({
    resolver: zodResolver(maintenanceSchema),
    defaultValues: { servers: [], projects: [], starts_at: defaults.start, ends_at: defaults.end, reason: "" },
  });

  const onSubmit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        scope: { ...(v.servers.length ? { servers: v.servers } : {}), ...(v.projects.length ? { projects: v.projects } : {}) },
        starts_at: new Date(v.starts_at).toISOString(),
        ends_at: new Date(v.ends_at).toISOString(),
        reason: v.reason,
      });
      onDone();
    } catch (e) {
      setFormError(submitMessage(e));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Yangi texnik ish" className="panel space-y-4 p-4">
      <h2 className="text-[15px] font-semibold">Yangi texnik ish oynasi</h2>
      <p className="text-muted">Oyna davomida tanlangan serverlar va loyihalar uchun bildirishnomalar yuborilmaydi.</p>

      <div className="grid gap-4 sm:grid-cols-2">
        <fieldset>
          <legend className="mb-1 text-[13px] font-medium">Serverlar</legend>
          {servers.isPending ? (
            <p className="text-muted">Yuklanmoqda…</p>
          ) : servers.error ? (
            <p role="alert" className="text-critical-fg">
              Serverlar ro&apos;yxati yuklanmadi.
            </p>
          ) : (
            <CheckList control={control} name="servers" options={servers.data!.map((s) => ({ value: s.id, label: s.name }))} />
          )}
        </fieldset>
        <fieldset>
          <legend className="mb-1 text-[13px] font-medium">Loyihalar</legend>
          {projects.isPending ? (
            <p className="text-muted">Yuklanmoqda…</p>
          ) : projects.error ? (
            <p role="alert" className="text-critical-fg">
              Loyihalar ro&apos;yxati yuklanmadi.
            </p>
          ) : (
            <CheckList control={control} name="projects" options={projects.data!.map((p) => ({ value: p.id, label: p.name }))} />
          )}
        </fieldset>
      </div>
      {errors.servers?.message && (
        <p role="alert" className="text-[13px] text-critical-fg">
          {errors.servers.message}
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <FormField label="Boshlanishi" error={errors.starts_at?.message}>
          {(p) => <input type="datetime-local" className="field" {...p} {...register("starts_at")} />}
        </FormField>
        <FormField label="Tugashi" error={errors.ends_at?.message}>
          {(p) => <input type="datetime-local" className="field" {...p} {...register("ends_at")} />}
        </FormField>
      </div>
      <FormField label="Sabab" error={errors.reason?.message}>
        {(p) => <input className="field" maxLength={300} placeholder="Masalan: OS yangilash va qayta yuklash" {...p} {...register("reason")} />}
      </FormField>

      {formError && (
        <p role="alert" className="rounded bg-critical-bg px-3 py-2 text-critical-fg">
          {formError}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Saqlanmoqda…" : "Saqlash"}
        </button>
        <button type="button" className="btn" onClick={onDone}>
          Bekor qilish
        </button>
      </div>
    </form>
  );
}

function MaintenanceTab({ canWrite, tz }: { canWrite: boolean; tz: string }) {
  const now = useNow();
  const windows = useMaintenance();
  const servers = useServers();
  const projects = useProjects("active");
  const cancel = useCancelMaintenance();
  const [creating, setCreating] = useState(false);
  const [target, setTarget] = useState<MaintenanceWindow | null>(null);
  const serverName = useMemo(() => new Map((servers.data ?? []).map((s) => [s.id, s.name])), [servers.data]);
  const projectName = useMemo(() => new Map((projects.data ?? []).map((p) => [p.id, p.name])), [projects.data]);

  return (
    <div className="space-y-3">
      {canWrite && !creating && (
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          Yangi texnik ish
        </button>
      )}
      {creating && <MaintenanceFormPanel onDone={() => setCreating(false)} />}

      {windows.isPending ? (
        <SkeletonRows rows={3} className="h-16" />
      ) : windows.error && !windows.data ? (
        <ErrorState error={windows.error} onRetry={() => void windows.refetch()} title="Texnik ishlar ro'yxatini yuklab bo'lmadi" />
      ) : windows.data!.length === 0 ? (
        <EmptyState title="Rejalashtirilgan texnik ish yo'q" hint="Server yoki loyihada rejali ish bo'lsa, oyna oching: shu vaqtda bildirishnomalar yuborilmaydi." />
      ) : (
        <ul className="m-0 list-none space-y-2 p-0">
          {windows.data!.map((w) => {
            const phase = windowPhase(w, now);
            const names = [...(w.scope.servers ?? []).map((id) => serverName.get(id) ?? "server"), ...(w.scope.projects ?? []).map((id) => projectName.get(id) ?? "loyiha")];
            return (
              <li key={w.id} data-testid="maintenance-row" className="panel flex flex-wrap items-start justify-between gap-3 p-3">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {names.join(", ") || "—"}
                    <StatusBadge status={phase === "active" ? "paused" : "info"} label={phase === "active" ? "Davom etmoqda" : "Rejalashtirilgan"} size="sm" />
                  </p>
                  <p className="text-muted">{w.reason}</p>
                  <p className="num text-[13px] text-muted">
                    {formatDateTime(w.starts_at, tz)} — {formatDateTime(w.ends_at, tz)}
                    {w.created_by && ` · ${w.created_by}`}
                  </p>
                </div>
                {canWrite && (
                  <button type="button" className="btn" onClick={() => setTarget(w)}>
                    Bekor qilish
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <ConfirmDialog
        open={target != null}
        title="Texnik ish bekor qilinadimi?"
        confirmLabel="Bekor qilish"
        cancelLabel="Qoldirish"
        danger
        busy={cancel.isPending}
        error={cancel.isError ? submitMessage(cancel.error) : null}
        onCancel={() => setTarget(null)}
        onConfirm={() => target && cancel.mutate(target.id, { onSuccess: () => setTarget(null) })}
      >
        <p>Oyna yopiladi va bildirishnomalar qayta yoqiladi.</p>
      </ConfirmDialog>
    </div>
  );
}

export default function MaintenancePage() {
  usePageTitle("Texnik ish");
  const me = useCurrentUser();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "silences" ? "silences" : "maintenance";
  const canWrite = me.role !== "viewer";

  return (
    <div className="space-y-4">
      <PageHeader title="Texnik ish va silence" />
      <Tabs
        label="Bo'limlar"
        value={tab}
        onChange={(k) => setParams(k === "silences" ? { tab: "silences" } : {}, { replace: true })}
        items={[
          { key: "maintenance", label: "Texnik ish" },
          { key: "silences", label: "Silence" },
        ]}
      />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {!canWrite && <p className="mb-3 text-muted">Kuzatuvchi roli faqat ro&apos;yxatni ko&apos;ra oladi.</p>}
        {tab === "silences" ? <SilencesTab canWrite={canWrite} tz={me.timezone} /> : <MaintenanceTab canWrite={canWrite} tz={me.timezone} />}
      </div>
    </div>
  );
}
