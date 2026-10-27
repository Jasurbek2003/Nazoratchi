import { useState } from "react";
import { useServerAction } from "../../api/queries";
import type { Role, Server } from "../../api/types";
import { ApiError } from "../../api/client";
import { ConfirmDialog } from "../../components/Controls";

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.details[0];
    return d ? `${e.message} ${d.message}` : e.message;
  }
  return "Amalni bajarib bo'lmadi. Aloqani tekshirib, qayta urinib ko'ring.";
}

/** Pauza / davom ettirish (owner, operator). Tasdiqlash dialogi oqibatni yozadi. */
export function PauseControls({ server, role }: { server: Server; role: Role }) {
  const [dialog, setDialog] = useState<"pause" | "resume" | null>(null);
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const pause = useServerAction(server.id, "pause");
  const resume = useServerAction(server.id, "resume");
  if (role === "viewer" || server.status === "archived") return null;

  const close = () => {
    setDialog(null);
    pause.reset();
    resume.reset();
    setReason("");
    setUntil("");
  };
  const reasonOk = reason.trim().length > 0 && reason.trim().length <= 200;

  return (
    <>
      {server.status === "paused" ? (
        <button type="button" className="btn" onClick={() => setDialog("resume")}>
          Davom ettirish
        </button>
      ) : (
        <button type="button" className="btn" onClick={() => setDialog("pause")}>
          Pauzaga qo&apos;yish
        </button>
      )}

      <ConfirmDialog
        open={dialog === "pause"}
        title={`${server.name} serverini pauzaga qo'yish`}
        confirmLabel="Pauzaga qo'yish"
        busy={pause.isPending}
        confirmDisabled={!reasonOk}
        error={pause.isError ? errorText(pause.error) : null}
        onCancel={close}
        onConfirm={() =>
          pause.mutate({ reason: reason.trim(), ...(until ? { until: new Date(until).toISOString() } : {}) }, { onSuccess: close })
        }
      >
        <p className="text-muted">Pauza vaqtida bu serverning alertlari bostiriladi. Ma&apos;lumot yig&apos;ilishda davom etadi.</p>
        <div>
          <label htmlFor="pause-reason" className="mb-1 block font-medium">
            Sabab
          </label>
          <input id="pause-reason" className="field" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Masalan: rejali texnik ish" />
        </div>
        <div>
          <label htmlFor="pause-until" className="mb-1 block font-medium">
            Avtomatik davom etish vaqti (ixtiyoriy, 90 kungacha)
          </label>
          <input id="pause-until" type="datetime-local" className="field" value={until} onChange={(e) => setUntil(e.target.value)} />
        </div>
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "resume"}
        title={`${server.name} serverini davom ettirish`}
        confirmLabel="Davom ettirish"
        busy={resume.isPending}
        error={resume.isError ? errorText(resume.error) : null}
        onCancel={close}
        onConfirm={() => resume.mutate(undefined, { onSuccess: close })}
      >
        <p>Alertlar qayta yoqiladi. Server holati keyingi ma&apos;lumot kelgach yangilanadi.</p>
      </ConfirmDialog>
    </>
  );
}
