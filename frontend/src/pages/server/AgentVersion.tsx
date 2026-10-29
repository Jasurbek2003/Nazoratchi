import { useState } from "react";
import { ApiError } from "../../api/client";
import { useAgentUpdate } from "../../api/queries";
import type { Role, Server } from "../../api/types";
import { ConfirmDialog } from "../../components/Controls";
import { StatusBadge } from "../../components/Status";
import { formatNumber } from "../../lib/format";

/** `X-Nazoratchi-Agent: nazoratchi-agent/1.2.3` sarlavhasidan faqat versiyani ajratadi. */
export function agentVersionText(raw: string): string {
  return raw.replace(/^nazoratchi-agent\//, "") || "—";
}

/** Soat farqi chegarasi (FR-AGT-012): agentning o'zi ham shu qiymatdan oshsa ogohlantiradi. */
export const CLOCK_SKEW_LIMIT_S = 5;

function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Amalni bajarib bo'lmadi. Aloqani tekshirib, qayta urinib ko'ring.";
}

/** Eskirgan agent belgisi (ro'yxat va sarlavha uchun). */
export function OutdatedBadge({ server }: { server: Pick<Server, "agent_outdated" | "agent_latest" | "agent_update_to"> }) {
  if (server.agent_update_to) return <StatusBadge status="info" label={`Yangilanmoqda → ${server.agent_update_to}`} size="sm" />;
  if (server.agent_outdated) return <StatusBadge status="warning" label="Yangilash kerak" size="sm" />;
  return null;
}

/** Agent versiyasi, "Yangilash kerak" belgisi va (faqat owner uchun) yangilash tugmasi (FR-AGT-008, FR-AGT-011). */
export function AgentVersion({ server, role }: { server: Server; role: Role }) {
  const [open, setOpen] = useState(false);
  const { request, cancel } = useAgentUpdate(server.id);
  const pending = Boolean(server.agent_update_to);
  const canUpdate = role === "owner" && server.status !== "archived";

  const close = () => {
    setOpen(false);
    request.reset();
  };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="num">{agentVersionText(server.agent_version)}</span>
      <OutdatedBadge server={server} />
      {server.agent_outdated && server.agent_latest && !pending && <span className="text-muted">oxirgisi: {server.agent_latest}</span>}
      {canUpdate && server.agent_outdated && !pending && (
        <button type="button" className="btn" onClick={() => setOpen(true)}>
          Yangilash
        </button>
      )}
      {canUpdate && pending && (
        <>
          <button type="button" className="btn" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            Bekor qilish
          </button>
          {cancel.isError && (
            <span role="alert" className="text-critical-fg">
              {errorText(cancel.error)}
            </span>
          )}
        </>
      )}

      <ConfirmDialog
        open={open}
        title={`${server.name}: agentni ${server.agent_latest ?? "yangi versiya"}ga yangilash`}
        confirmLabel="Yangilash"
        busy={request.isPending}
        error={request.isError ? errorText(request.error) : null}
        onCancel={close}
        onConfirm={() => request.mutate(undefined, { onSuccess: close })}
      >
        <p className="text-muted">
          Agent yangi versiyani yuklaydi, imzosini tekshiradi va qayta ishga tushadi (taxminan bir daqiqa). Bu vaqtda ma&apos;lumot navbatda saqlanadi, yo&apos;qolmaydi.
        </p>
        <p className="text-muted">Yangi agent core&apos;ga ulana olmasa, avtomatik eski versiyaga qaytadi.</p>
      </ConfirmDialog>
    </div>
  );
}

/** Soat farqi (FR-AGT-012): chegaradan oshsa ogohlantirish. `null` — yangi o'lchov yo'q. */
export function ClockSkew({ seconds }: { seconds: number | null }) {
  if (seconds === null) return <span className="text-muted">—</span>;
  const off = Math.abs(seconds) > CLOCK_SKEW_LIMIT_S;
  const sign = seconds > 0 ? "+" : seconds < 0 ? "−" : "";
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="num">
        {sign}
        {formatNumber(Math.abs(seconds), 1)} s
      </span>
      {off ? (
        <>
          <StatusBadge status="warning" label="Soat siljigan" size="sm" />
          <span className="text-muted">Vaqt sinxronligini tekshiring (chrony yoki systemd-timesyncd): vaqt belgilari noto&apos;g&apos;ri bo&apos;lishi mumkin.</span>
        </>
      ) : (
        <span className="text-muted">me&apos;yorda</span>
      )}
    </div>
  );
}
