import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "../api/client";
import { useCreateDrill } from "../api/queries";
import type { BackupDetail } from "../api/types";
import { FormField } from "../components/FormField";
import { StatusBadge } from "../components/Status";
import { DRILL_RESULT, drillBadge, drillBody, drillSchema, formatDuration, type DrillForm } from "../lib/backups";
import { formatDateTime, formatNumber } from "../lib/format";
import { toLocalInput } from "../lib/suppression";

function submitMessage(e: unknown): string {
  if (e instanceof ApiError) return e.status === 403 ? "Bu amal uchun ruxsat yo'q." : e.message;
  return "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.";
}

function DrillFormPanel({ project, onDone }: { project: string; onDone: () => void }) {
  const create = useCreateDrill();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<DrillForm>({
    resolver: zodResolver(drillSchema),
    defaultValues: { performed_at: toLocalInput(new Date()), backup_file: "", result: "success", backup_age_h: "", duration_s: "", tables_count: "", rows_count: "", notes: "" },
  });

  const onSubmit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync(drillBody(project, v));
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        for (const d of e.details) {
          if (d.field in v) setError(d.field as keyof DrillForm, { message: d.message });
        }
      }
      setFormError(submitMessage(e));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Drill natijasini kiritish" className="mt-3 space-y-3 rounded border border-line p-3">
      <p className="text-muted">Zaxirani vaqtinchalik muhitda tiklab ko&apos;rgandan keyin natijani kiriting (TZ 10.8).</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField label="Bajarilgan vaqt" error={errors.performed_at?.message}>
          {(p) => <input type="datetime-local" className="field" {...p} {...register("performed_at")} />}
        </FormField>
        <FormField label="Natija" error={errors.result?.message}>
          {(p) => (
            <select className="field" {...p} {...register("result")}>
              <option value="success">Muvaffaqiyatli</option>
              <option value="partial">Qisman</option>
              <option value="failed">Muvaffaqiyatsiz</option>
            </select>
          )}
        </FormField>
      </div>
      <FormField label="Tiklangan zaxira fayli" error={errors.backup_file?.message} hint="Masalan: BiznesRadar-20261022-031501.sql.gz">
        {(p) => <input className="field mono" autoComplete="off" {...p} {...register("backup_file")} />}
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <FormField label="Zaxira yoshi (soat)" error={errors.backup_age_h?.message}>
          {(p) => <input inputMode="numeric" className="field" {...p} {...register("backup_age_h")} />}
        </FormField>
        <FormField label="Davomiylik (soniya)" error={errors.duration_s?.message} hint="RTO bahosi">
          {(p) => <input inputMode="numeric" className="field" {...p} {...register("duration_s")} />}
        </FormField>
        <FormField label="Jadvallar soni" error={errors.tables_count?.message}>
          {(p) => <input inputMode="numeric" className="field" {...p} {...register("tables_count")} />}
        </FormField>
        <FormField label="Qatorlar soni" error={errors.rows_count?.message}>
          {(p) => <input inputMode="numeric" className="field" {...p} {...register("rows_count")} />}
        </FormField>
      </div>
      <FormField label="Izoh" error={errors.notes?.message}>
        {(p) => <textarea rows={3} className="field" {...p} {...register("notes")} />}
      </FormField>
      {formError && (
        <p role="alert" className="text-critical-fg">
          {formError}
        </p>
      )}
      <div className="flex gap-2">
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

export function DrillSection({ backup, canWrite, tz }: { backup: BackupDetail; canWrite: boolean; tz: string }) {
  const [adding, setAdding] = useState(false);
  const badge = drillBadge(backup.drill);
  return (
    <section className="panel p-4 lg:col-span-2" aria-labelledby="bk-drill">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="bk-drill" className="text-[15px] font-semibold">
            Restore drill
          </h2>
          <StatusBadge status={badge.status} label={badge.label} size="sm" />
        </div>
        {canWrite && !adding && (
          <button type="button" className="btn" onClick={() => setAdding(true)}>
            Drill natijasini kiritish
          </button>
        )}
      </div>
      <p className="mt-1 text-[13px] text-muted">Zaxira haqiqatan tiklanishini tekshirish; har {backup.drill.every_days} kunda bir marta.</p>
      {adding && <DrillFormPanel project={backup.project} onDone={() => setAdding(false)} />}
      {backup.drills.length === 0 ? (
        <p className="mt-3 text-muted">Hali drill o&apos;tkazilmagan.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <caption className="sr-only">Restore drill tarixi</caption>
            <thead>
              <tr className="border-b border-line text-[13px] text-muted">
                {["Sana", "Natija", "Davomiylik", "Jadval / qator", "Fayl", "Kim"].map((h) => (
                  <th key={h} scope="col" className="py-2 pr-3 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {backup.drills.map((d) => {
                const r = DRILL_RESULT[d.result];
                return (
                  <tr key={d.id} data-testid="drill-row" className="border-b border-line align-top last:border-0">
                    <td className="num py-1.5 pr-3">{formatDateTime(d.performed_at, tz)}</td>
                    <td className="py-1.5 pr-3">
                      <StatusBadge status={r.status} label={r.label} size="sm" />
                    </td>
                    <td className="num py-1.5 pr-3">{formatDuration(d.duration_s)}</td>
                    <td className="num py-1.5 pr-3">
                      {d.tables_count != null ? formatNumber(d.tables_count) : "—"} / {d.rows_count != null ? formatNumber(d.rows_count) : "—"}
                    </td>
                    <td className="mono max-w-[260px] truncate py-1.5 pr-3" title={d.notes ? `${d.backup_file}\n${d.notes}` : d.backup_file}>
                      {d.backup_file}
                    </td>
                    <td className="py-1.5">{d.performed_by ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
