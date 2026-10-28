import type { Cert, Domain, Probe } from "../api/types";
import { effectiveProbeStatus, probeStale } from "./projectStatus";
import { PROBE_STATE_LABEL, type Status } from "./status";

export interface DomainRowData {
  domain: Domain;
  http: Probe | null;
  dns: Probe | null;
  certs: Cert[];
  minDaysLeft: number | null;
}

/** Domen -> uning HTTP/DNS tekshiruvi va sertifikatlari (probe.domain, cert.domain = domen id si). */
export function buildDomainRows(domains: Domain[], probes: Probe[], certs: Cert[]): DomainRowData[] {
  return domains.map((domain) => {
    const mine = probes.filter((p) => p.domain === domain.id);
    const dc = certs.filter((c) => c.domain === domain.id);
    return {
      domain,
      http: mine.find((p) => p.type === "http") ?? null,
      dns: mine.find((p) => p.type === "dns") ?? null,
      certs: dc,
      minDaysLeft: dc.length ? Math.min(...dc.map((c) => c.days_left)) : null,
    };
  });
}

export function probeBadge(p: Probe | null, now: number): { status: Status; label: string } {
  if (!p) return { status: "unknown", label: "Sozlanmagan" };
  const status = effectiveProbeStatus(p, now);
  if (!p.enabled) return { status, label: "O'chirilgan" };
  if (probeStale(p, now)) return { status, label: "Eskirgan" };
  return { status, label: PROBE_STATE_LABEL[p.state] ?? p.state };
}

export function dnsProblem(row: DomainRowData, now: number): boolean {
  return row.dns != null && effectiveProbeStatus(row.dns, now) === "critical";
}

export function certExpiring(row: DomainRowData): boolean {
  return row.minDaysLeft != null && row.minDaysLeft <= 21;
}

/** Kutilgan IP lar (ro'yxat yoki matn bo'lishi mumkin). */
export function ipList(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  if (typeof value === "string" && value) return [value];
  return [];
}
