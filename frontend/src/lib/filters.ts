/** Ro'yxat filtrlari: holat, teg, qidiruv (`q`). Holat URL'da (TZ 13.8). */
import type { Project, Server } from "../api/types";

export interface ServerFilter {
  status?: string;
  tag?: string;
  q?: string;
}

function norm(s: string): string {
  return s.trim().toLocaleLowerCase("uz");
}

export function filterServers(servers: Server[], f: ServerFilter): Server[] {
  const q = norm(f.q ?? "");
  return servers.filter((s) => {
    if (f.status && s.status !== f.status) return false;
    if (f.tag && !s.tags.includes(f.tag)) return false;
    if (!q) return true;
    const hay = [s.name, s.provider, s.public_ipv4 ?? "", s.public_ipv6 ?? "", s.role, s.location, ...s.tags];
    return hay.some((h) => norm(h).includes(q));
  });
}

export interface ProjectFilter {
  q?: string;
  kind?: string;
}

export function filterProjects(projects: Project[], f: ProjectFilter): Project[] {
  const q = norm(f.q ?? "");
  return projects.filter((p) => {
    if (f.kind && p.kind !== f.kind) return false;
    if (!q) return true;
    const hay = [
      p.slug,
      p.name,
      p.owner_name,
      ...p.tags,
      ...p.domains_info.map((d) => d.fqdn),
      ...p.servers_info.map((s) => s.server),
    ];
    return hay.some((h) => norm(h).includes(q));
  });
}

export function collectTags(servers: Server[]): string[] {
  return [...new Set(servers.flatMap((s) => s.tags))].sort((a, b) => a.localeCompare(b));
}
