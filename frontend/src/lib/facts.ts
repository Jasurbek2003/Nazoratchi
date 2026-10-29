import { formatBytes, formatNumber } from "./format";

const LABELS: Record<string, string> = {
  os: "Operatsion tizim",
  arch: "Arxitektura",
  cpu_count: "CPU yadrolari",
  mem_total_bytes: "Operativ xotira",
  kernel_running: "Kernel (ishlayotgan)",
  kernel_latest_installed: "Kernel (oxirgi o'rnatilgan)",
  hostname: "Host nomi",
  virtualization: "Virtualizatsiya",
  cpu_model: "CPU modeli",
  docker_version: "Docker versiyasi",
  agent_build_time: "Agent yig'ilgan vaqt",
  go_version: "Go versiyasi (agent)",
};

export interface FactRow {
  key: string;
  label: string;
  value: string;
}

/** `facts` JSON'ni ko'rsatish uchun tekis ro'yxatga aylantiradi (chuqurlik <= 2; ro'yxatlar vergul bilan). */
export function flattenFacts(facts: Record<string, unknown> | null | undefined): FactRow[] {
  const rows: FactRow[] = [];
  const walk = (obj: Record<string, unknown>, prefix: string, depth: number) => {
    for (const [k, v] of Object.entries(obj)) {
      const path = prefix ? `${prefix}.${k}` : k;
      if (v !== null && typeof v === "object" && !Array.isArray(v) && depth < 2) {
        walk(v as Record<string, unknown>, path, depth + 1);
        continue;
      }
      rows.push({ key: path, label: LABELS[path] ?? path.replace(/[_.]/g, " "), value: factValue(path, v) });
    }
  };
  if (facts) walk(facts, "", 0);
  return rows.sort((a, b) => a.label.localeCompare(b.label));
}

function factValue(path: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return /bytes$/.test(path) ? formatBytes(v) : formatNumber(v, 2);
  if (typeof v === "boolean") return v ? "ha" : "yo'q";
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ") || "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
