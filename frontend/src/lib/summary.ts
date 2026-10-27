/** Dashboard xulosasi (TZ 13.1 №1-2): "Hammasi joyida" yoki "N ta muammo"; muammolar ahamiyat bo'yicha. */
import type { Incident, Server } from "../api/types";
import { isStale } from "./freshness";
import { severityRank, severityStatus, worstStatus, type Status } from "./status";

export interface Problem {
  key: string;
  kind: "incident" | "server";
  status: Status;
  title: string;
  since: string | null;
  serverId?: string;
  incident?: Incident;
}

export interface Summary {
  level: Status;
  headline: string;
  /** Hisobga olinadigan muammolar (bostirilmaganlar), og'iri tepada. */
  problems: Problem[];
  /** Silence/maintenance tufayli bostirilgan incidentlar soni. */
  suppressed: number;
}

export function hostOf(incident: Pick<Incident, "scope_key">): string | null {
  return incident.scope_key.startsWith("host:") ? incident.scope_key.slice(5) : null;
}

/** Og'iri birinchi; teng bo'lsa yangisi birinchi. */
export function compareProblems(a: Problem, b: Problem): number {
  const bySeverity = severityRankOfStatus(b.status) - severityRankOfStatus(a.status);
  if (bySeverity !== 0) return bySeverity;
  return Date.parse(b.since ?? "") - Date.parse(a.since ?? "") || 0;
}

function severityRankOfStatus(s: Status): number {
  return s === "unknown" ? 0 : severityRank(s) + 1;
}

export function countLabel(n: number): string {
  return `${n} ta muammo`;
}

export function buildSummary(input: { incidents: Incident[]; servers: Server[]; now: number }): Summary {
  const { incidents, servers, now } = input;
  const unresolved = incidents.filter((i) => i.status !== "resolved");
  const active = unresolved.filter((i) => !i.suppressed);
  const problems: Problem[] = active.map((incident) => ({
    key: `incident:${incident.id}`,
    kind: "incident",
    status: severityStatus(incident.severity),
    title: incident.title,
    since: incident.started_at,
    serverId: hostOf(incident) ?? undefined,
    incident,
  }));

  // Incident yaratilmagan bo'lsa ham, aloqasi uzilgan serverni yashirmaymiz.
  const covered = new Set(unresolved.map(hostOf).filter((x): x is string => x !== null));
  for (const server of servers) {
    if (covered.has(server.id)) continue;
    if (server.status === "offline") {
      problems.push({
        key: `server:${server.id}`,
        kind: "server",
        status: "critical",
        title: `Server aloqada emas: ${server.name}`,
        since: server.last_seen_at,
        serverId: server.id,
      });
    } else if (server.status === "online" && isStale(server.last_seen_at, now)) {
      problems.push({
        key: `server:${server.id}`,
        kind: "server",
        status: "unknown",
        title: `Ma'lumot kelmayapti: ${server.name}`,
        since: server.last_seen_at,
        serverId: server.id,
      });
    }
  }

  problems.sort(compareProblems);
  const level = problems.length === 0 ? "ok" : worstStatus(problems.map((p) => p.status));
  return {
    level,
    headline: problems.length === 0 ? "Hammasi joyida" : countLabel(problems.length),
    problems,
    suppressed: unresolved.length - active.length,
  };
}
