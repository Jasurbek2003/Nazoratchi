import type { IncidentEvent } from "../api/types";

const SEVERITY_LABEL: Record<string, string> = { info: "ma'lumot", warning: "diqqat", high: "muhim", critical: "kritik" };

function str(v: unknown): string {
  return typeof v === "string" || typeof v === "number" ? String(v) : "";
}

/** Incident voqeasining o'zbekcha tavsifi (backend voqea turlari: apps/alerts/engine.py, services.py). */
export function describeEvent(e: Pick<IncidentEvent, "type" | "user" | "data">): string {
  const d = e.data ?? {};
  const alert = str(d["alert"]);
  const subject = str(d["subject"]);
  const who = e.user ? `${e.user} ` : "";
  switch (e.type) {
    case "opened":
      return `Ochildi${alert ? `: ${alert}` : ""}`;
    case "alert_added":
      return `Alert qo'shildi: ${alert}${subject ? ` (${subject})` : ""}`;
    case "alert_resolved":
      return `Alert tiklandi: ${alert}${subject ? ` (${subject})` : ""}`;
    case "severity_changed":
      return `Ahamiyat o'zgardi: ${SEVERITY_LABEL[str(d["old"])] ?? str(d["old"])} → ${SEVERITY_LABEL[str(d["new"])] ?? str(d["new"])}`;
    case "notified":
      return `Bildirishnoma yuborildi${alert ? `: ${alert}` : ""}`;
    case "reminder":
      return `Eslatma yuborildi${d["n"] ? ` (${str(d["n"])}-marta)` : ""}`;
    case "acked":
      return `${who}qabul qildi${d["comment"] ? `: «${str(d["comment"])}»` : ""}`;
    case "comment":
      return `${who}izoh yozdi: «${str(d["text"])}»`;
    case "resolved":
      return d["manual"] ? `${who}qo'lda yopdi` : "Avtomatik yopildi";
    default:
      return e.type;
  }
}

export function scopeLabel(scopeKey: string, serverName?: string): string {
  if (scopeKey.startsWith("host:")) return serverName ?? "server";
  if (scopeKey.startsWith("job:")) return "zaxira ishi";
  if (scopeKey.startsWith("channel:")) return "bildirishnoma kanali";
  if (scopeKey === "system") return "tizim";
  return scopeKey;
}
