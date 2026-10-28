import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAlertRules, useChannels, useCreateChannel, useDeleteChannel, useTestChannel, useToggleRule, useUpdateChannel } from "../api/queries";
import type { NotificationChannel } from "../api/types";
import { useCurrentUser, usePageTitle } from "../app/context";
import { ConfirmDialog, Tabs } from "../components/Controls";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { FormField, PageHeader } from "../components/FormField";
import { StatusBadge } from "../components/Status";
import { formatAgoFrom, formatDateTime, formatDuration } from "../lib/format";
import { severityStatus } from "../lib/status";
import { useNow } from "../lib/useNow";

const SEVERITY_CHOICES = [
  { value: "info", label: "Ma'lumot va undan yuqori" },
  { value: "warning", label: "Diqqat va undan yuqori" },
  { value: "high", label: "Muhim va undan yuqori" },
  { value: "critical", label: "Faqat kritik" },
];

const BOT_TOKEN_RE = /^\d{6,12}:[A-Za-z0-9_-]{30,50}$/;
const CHAT_USERNAME_RE = /^@[A-Za-z][A-Za-z0-9_]{4,31}$/;

export const channelSchema = z.object({
  name: z.string().trim().min(1, "Nomni kiriting.").max(80, "Nom 80 belgidan oshmasin."),
  min_severity: z.enum(["info", "warning", "high", "critical"]),
  bot_token: z.string().trim().regex(BOT_TOKEN_RE, "Token noto'g'ri. BotFather formati: 123456:ABC-DEF…"),
  chat_id: z
    .string()
    .trim()
    .refine((v) => /^-?\d+$/.test(v) || CHAT_USERNAME_RE.test(v), "Chat ID butun son (masalan, -1001234567) yoki @kanal_nomi bo'lishi kerak."),
});
export type ChannelForm = z.infer<typeof channelSchema>;

function message(e: unknown): string {
  if (e instanceof ApiError) return e.status === 403 ? "Bu amal uchun ruxsat yo'q." : e.message;
  return "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.";
}

// ------------------------------------------------------------------ kanallar
function ChannelFormPanel({ onDone }: { onDone: () => void }) {
  const create = useCreateChannel();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ChannelForm>({ resolver: zodResolver(channelSchema), defaultValues: { name: "", min_severity: "warning", bot_token: "", chat_id: "" } });

  const onSubmit = handleSubmit(async (v) => {
    setFormError(null);
    try {
      await create.mutateAsync({
        type: "telegram",
        name: v.name,
        min_severity: v.min_severity,
        config: { bot_token: v.bot_token, chat_id: /^-?\d+$/.test(v.chat_id) ? Number(v.chat_id) : v.chat_id },
      });
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setError("name", { message: "Bunday nomli kanal mavjud." });
      else setFormError(message(e));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Yangi Telegram kanali" className="panel space-y-4 p-4">
      <h2 className="text-[15px] font-semibold">Yangi Telegram kanali</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField label="Nomi" error={errors.name?.message}>
          {(p) => <input className="field" autoComplete="off" {...p} {...register("name")} />}
        </FormField>
        <FormField label="Eng past ahamiyat">
          {(p) => (
            <select className="field" {...p} {...register("min_severity")}>
              {SEVERITY_CHOICES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <FormField label="Bot tokeni" error={errors.bot_token?.message} hint="Saqlangandan keyin token hech qayerda ko'rsatilmaydi.">
          {(p) => <input type="password" className="field" autoComplete="off" spellCheck={false} {...p} {...register("bot_token")} />}
        </FormField>
        <FormField label="Chat ID" error={errors.chat_id?.message} hint="Shaxsiy yoki guruh ID si, yoki @kanal_nomi.">
          {(p) => <input className="field" autoComplete="off" spellCheck={false} {...p} {...register("chat_id")} />}
        </FormField>
      </div>
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

function ChannelRow({ channel, now, tz }: { channel: NotificationChannel; now: number; tz: string }) {
  const test = useTestChannel();
  const update = useUpdateChannel();
  const del = useDeleteChannel();
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const masked = channel.config_masked;

  const runTest = () => {
    setResult(null);
    test.mutate(channel.id, {
      onSuccess: () => setResult({ ok: true, text: "Sinov xabari yuborildi." }),
      onError: (e) => setResult({ ok: false, text: e instanceof ApiError && e.status === 502 ? "Sinov xabari yuborilmadi. Token va chat ID ni tekshiring." : message(e) }),
    });
  };

  return (
    <li data-testid="channel-row" className="panel p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            {channel.name}
            <span className="text-xs font-normal text-muted">Telegram</span>
            <StatusBadge status={channel.enabled ? "ok" : "paused"} label={channel.enabled ? "Yoqilgan" : "O'chirilgan"} size="sm" />
          </p>
          <p className="text-muted">
            {masked.error ? <span className="text-warning-fg">{masked.error}</span> : <>Chat: <span className="mono">{String(masked.chat_id ?? "—")}</span> · Token: yashirin</>}
            {" · "}ahamiyat: {SEVERITY_CHOICES.find((s) => s.value === channel.min_severity)?.label.toLowerCase() ?? channel.min_severity}
          </p>
          <p className="text-[13px] text-muted num" title={channel.last_ok_at ? formatDateTime(channel.last_ok_at, tz) : undefined}>
            Oxirgi muvaffaqiyatli yuborish: {formatAgoFrom(channel.last_ok_at, now)}
          </p>
          {channel.last_error && (
            <p className="text-[13px] text-critical-fg">
              Oxirgi xato: {channel.last_error}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn" disabled={test.isPending} onClick={runTest}>
            {test.isPending ? "Yuborilmoqda…" : "Sinash"}
          </button>
          <button type="button" className="btn" disabled={update.isPending} onClick={() => update.mutate({ id: channel.id, enabled: !channel.enabled })}>
            {channel.enabled ? "O'chirish" : "Yoqish"}
          </button>
          <button type="button" className="btn" onClick={() => setConfirm(true)}>
            O&apos;chirib tashlash
          </button>
        </div>
      </div>
      {result && (
        <p role={result.ok ? "status" : "alert"} className={`mt-2 ${result.ok ? "text-ok-fg" : "text-critical-fg"}`}>
          {result.text}
        </p>
      )}
      {update.isError && (
        <p role="alert" className="mt-2 text-critical-fg">
          {message(update.error)}
        </p>
      )}
      <ConfirmDialog
        open={confirm}
        title={`«${channel.name}» kanali o'chirilsinmi?`}
        confirmLabel="O'chirib tashlash"
        danger
        busy={del.isPending}
        error={del.isError ? message(del.error) : null}
        onCancel={() => setConfirm(false)}
        onConfirm={() => del.mutate(channel.id, { onSuccess: () => setConfirm(false) })}
      >
        <p>Kanal va uning sozlamalari o&apos;chiriladi: shu kanalga bildirishnomalar kelmaydi. Davom etasizmi?</p>
      </ConfirmDialog>
    </li>
  );
}

function ChannelsTab({ isOwner, tz }: { isOwner: boolean; tz: string }) {
  const now = useNow();
  const channels = useChannels(isOwner);
  const [creating, setCreating] = useState(false);

  if (!isOwner) {
    return <EmptyState title="Kanallarni faqat egasi boshqaradi" hint="Bildirishnoma kanallari sozlamalari uchun egasiga murojaat qiling." />;
  }
  return (
    <div className="space-y-3">
      {!creating && (
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          Telegram kanalini qo&apos;shish
        </button>
      )}
      {creating && <ChannelFormPanel onDone={() => setCreating(false)} />}
      {channels.isPending ? (
        <SkeletonRows rows={2} className="h-24" />
      ) : channels.error && !channels.data ? (
        <ErrorState error={channels.error} onRetry={() => void channels.refetch()} title="Kanallarni yuklab bo'lmadi" />
      ) : channels.data!.length === 0 ? (
        <EmptyState title="Birinchi bildirishnoma kanalini qo'shing" hint="Kanalsiz alertlar faqat shu yerda ko'rinadi, Telegram'ga xabar bormaydi." />
      ) : (
        <ul className="m-0 list-none space-y-2 p-0">
          {channels.data!.map((c) => (
            <ChannelRow key={c.id} channel={c} now={now} tz={tz} />
          ))}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ qoidalar
function RulesTab({ canWrite }: { canWrite: boolean }) {
  const rules = useAlertRules();
  const toggle = useToggleRule();

  if (rules.isPending) return <SkeletonRows rows={5} className="h-16" />;
  if (rules.error && !rules.data) return <ErrorState error={rules.error} onRetry={() => void rules.refetch()} title="Qoidalarni yuklab bo'lmadi" />;
  if (rules.data!.length === 0) return <EmptyState title="Alert qoidalari yo'q" hint="Standart qoidalar tizim o'rnatilganda yaratiladi." />;
  return (
    <div className="space-y-2">
      {toggle.isError && (
        <p role="alert" className="rounded bg-critical-bg px-3 py-2 text-critical-fg">
          {message(toggle.error)}
        </p>
      )}
      <ul className="m-0 list-none space-y-2 p-0">
        {rules.data!.map((r) => (
          <li key={r.id} data-testid="rule-row" className="panel flex flex-wrap items-start justify-between gap-3 p-3">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 font-medium">
                <span className="mono text-xs text-muted">{r.key}</span>
                {r.name}
                <StatusBadge status={severityStatus(r.severity)} size="sm" />
              </p>
              {r.description && <p className="text-muted">{r.description}</p>}
              <p className="num text-[13px] text-muted">
                Qamrov: {String(r.scope.type ?? "—")} · kutish: {formatDuration(r.for_seconds)} · tiklanish: {formatDuration(r.resolve_after_seconds)}
              </p>
            </div>
            {canWrite ? (
              <label className="inline-flex items-center gap-2 max-md:min-h-11">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[var(--accent)]"
                  checked={r.enabled}
                  disabled={toggle.isPending}
                  onChange={(e) => toggle.mutate({ id: r.id, enabled: e.target.checked })}
                  aria-label={`${r.name} qoidasi yoqilgan`}
                />
                Yoqilgan
              </label>
            ) : (
              <StatusBadge status={r.enabled ? "ok" : "paused"} label={r.enabled ? "Yoqilgan" : "O'chirilgan"} size="sm" />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SettingsPage() {
  usePageTitle("Sozlamalar");
  const me = useCurrentUser();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "rules" ? "rules" : "channels";

  return (
    <div className="space-y-4">
      <PageHeader title="Sozlamalar" />
      <Tabs
        label="Sozlamalar bo'limlari"
        value={tab}
        onChange={(k) => setParams(k === "rules" ? { tab: "rules" } : {}, { replace: true })}
        items={[
          { key: "channels", label: "Bildirishnoma kanallari" },
          { key: "rules", label: "Alert qoidalari" },
        ]}
      />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "rules" ? <RulesTab canWrite={me.role !== "viewer"} /> : <ChannelsTab isOwner={me.role === "owner"} tz={me.timezone} />}
      </div>
    </div>
  );
}
