/** Backend javob shakllari (backend/apps/* serializerlaridan olingan). Vaqtlar — ISO-8601 UTC. */

export type Role = "owner" | "operator" | "viewer";

export interface Me {
  id: string;
  login: string;
  role: Role;
  language: string;
  timezone: string;
  mfa_enabled: boolean;
}

export type ServerState = "new" | "online" | "offline" | "paused" | "archived";

export interface Server {
  id: string;
  name: string;
  provider: string;
  public_ipv4: string | null;
  public_ipv6: string | null;
  role: string;
  tags: string[];
  location: string;
  monthly_cost_usd: string | null;
  notes: string;
  status: ServerState;
  last_seen_at: string | null;
  paused_at: string | null;
  paused_until: string | null;
  pause_reason: string;
  agent_version: string;
  /** Owner so'ragan nishon versiya (yangilanish jarayonda), aks holda bo'sh. */
  agent_update_to: string;
  /** Core'dagi eng yangi agent relizi; reliz fayllari yo'q bo'lsa null. */
  agent_latest: string | null;
  /** true: eskirgan; false: yangi; null: noma'lum (dev build yoki reliz yo'q). */
  agent_outdated: boolean | null;
  facts: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ServerDetail extends Server {
  open_incidents: number;
  /** Agent o'lchagan soat farqi (core - agent, soniya); yangi o'lchov bo'lmasa null. */
  clock_skew_seconds: number | null;
}

export interface ServerEnvelope<T> {
  items: T[];
}

export type IncidentStatus = "open" | "acknowledged" | "resolved";

export interface Incident {
  id: string;
  scope_key: string;
  title: string;
  severity: string;
  status: IncidentStatus;
  started_at: string;
  acked_at: string | null;
  acked_by: string | null;
  resolved_at: string | null;
  suppressed: boolean;
  root_cause: string;
  summary: unknown;
}

export interface AlertInstance {
  id: string;
  rule: string;
  rule_key: string;
  rule_name: string;
  severity: string;
  subject_type: string;
  subject_id: string;
  subject_name: string;
  state: "ok" | "pending" | "firing" | "resolving";
  pending_since: string | null;
  firing_since: string | null;
  resolving_since: string | null;
  last_eval_at: string | null;
  last_value: number | null;
  detail: unknown;
  incident: string | null;
  suppressed: boolean;
  notified_at: string | null;
}

export interface IncidentEvent {
  id: number;
  time: string;
  type: string;
  user: string | null;
  data: Record<string, unknown>;
}

export interface IncidentDetail extends Incident {
  alerts: AlertInstance[];
  events: IncidentEvent[];
}

export interface LatestPoint {
  labels: Record<string, string>;
  time: string;
  value: number;
}

export interface LatestResponse {
  server_id: string;
  metrics: Record<string, LatestPoint[]>;
}

/** [epoch ms, qiymat | null]; null = ma'lumot yo'q (grafikda uzilish). */
export type RawPoint = [number, number | null];

export interface QuerySeries {
  labels: Record<string, string>;
  points: RawPoint[];
}

export interface QueryResponse {
  name: string;
  unit: string;
  step_seconds: number;
  source: string;
  series: QuerySeries[];
}

export interface Container {
  container: string;
  project: string;
  service: string;
  time: string;
  running: boolean;
  restarts?: number;
  uptime_seconds?: number;
  /** 0 — healthcheck yo'q, 1 — healthy, 2 — unhealthy, 3 — starting */
  health?: number;
  oom_killed?: number;
  expected?: number;
  stale: boolean;
}

export interface Filesystem {
  mount: string;
  device: string;
  fstype: string;
  time: string;
  total_bytes?: number;
  used_bytes?: number;
  avail_bytes?: number;
  used_percent?: number;
  readonly: boolean;
  days_until_full: number | null;
}

export interface ServerInfo {
  server_id: string;
  server: string;
  environment: string;
  ports: number[];
}

export interface DomainInfo {
  id: string;
  fqdn: string;
  status: string;
}

export interface Project {
  id: string;
  slug: string;
  name: string;
  description: string;
  owner_name: string;
  owner_contact: string;
  kind: "compose" | "systemd" | "static" | "other";
  moved: boolean;
  status: "active" | "archived";
  tags: string[];
  links: { label: string; url: string }[];
  notes: string;
  created_at: string;
  updated_at: string;
  servers_info: ServerInfo[];
  domains_info: DomainInfo[];
}

export interface ProbeResult {
  time: string;
  ok: boolean;
  status_code: number | null;
  total_ms: number | null;
  error_kind: string | null;
  detail: unknown;
}

export interface Probe {
  id: string;
  project: string | null;
  domain: string | null;
  type: "http" | "tcp" | "tls" | "dns" | "whois";
  name: string;
  config: Record<string, unknown>;
  interval_s: number;
  timeout_s: number;
  enabled: boolean;
  state: "up" | "down" | "unknown" | "paused";
  state_since: string | null;
  consecutive_failures: number;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  last_result: ProbeResult | null;
}

export interface Cert {
  id: number;
  name: string;
  source: string;
  domain: string | null;
  project: string | null;
  not_after: string;
  days_left: number;
  issuer: string;
  subject: string;
  san: string[];
  chain_ok: boolean | null;
  hostname_ok: boolean | null;
  checked_at: string;
}

export interface TopItem {
  server_id: string;
  server: string;
  labels: Record<string, string>;
  value: number;
  time: string;
}

// ------------------------------------------------------------------ S9: zaxira, domen, silence, kanal, qoida
export type BackupState = "ok" | "late" | "critical" | "failed" | "stale" | "missing" | "unknown" | "none";

export interface BackupItem {
  project: string;
  project_id: string;
  name: string;
  server: string | null;
  server_id: string | null;
  expect_daily: boolean;
  expect_weekly_files: boolean;
  require_offsite: boolean;
  state: BackupState;
  age_hours: number | null;
  last_success_at: string | null;
  last_size_bytes: number | null;
  last_status: "ok" | "fail" | null;
  daily_count: number;
  weekly_count: number;
  files_count: number;
  newest_age_seconds: Record<string, number>;
  offsite_configured: boolean | null;
  data_seen_at: string | null;
  drill: DrillSummary;
}

export type DrillResult = "success" | "partial" | "failed";

export interface Drill {
  id: string;
  project: string;
  performed_at: string;
  performed_by: string | null;
  backup_file: string;
  backup_age_h: number | null;
  duration_s: number | null;
  tables_count: number | null;
  rows_count: number | null;
  result: DrillResult;
  notes: string;
}

/** Karta/jadvaldagi drill holati (R-117: "hech qachon" aniq ko'rinadi). */
export interface DrillSummary {
  every_days: number;
  last: Drill | null;
  last_success_days: number | null;
  never: boolean;
  overdue: boolean;
}

export interface BackupDetail extends BackupItem {
  drills: Drill[];
  runs: { finished_at: string; size_bytes: number | null }[];
  size_median_7: number | null;
  size_ratio: number | null;
  size_anomaly: boolean;
}

export interface Domain {
  id: string;
  project: string | null;
  project_slug: string | null;
  fqdn: string;
  expected_ips: unknown;
  dns_provider: string;
  registrar: string;
  controlled_by: string;
  tls_enabled: boolean;
  status: string;
  notes: string;
  created_at: string;
}

export interface DnsResolverRow {
  resolver: string;
  rtype: string;
  time: string;
  answers: unknown;
  matches: boolean | null;
  rcode: string | number | null;
  latency_ms: number | null;
}

export interface DnsChangeRow {
  resolver: string;
  rtype: string;
  old_answers: unknown;
  new_answers: unknown;
  changed_at: string;
}

export interface DnsInfo {
  resolvers: DnsResolverRow[];
  changes: DnsChangeRow[];
}

export interface Matcher {
  label: string;
  op: "=" | "!=" | "=~";
  value: string;
}

export interface Silence {
  id: string;
  matchers: Matcher[];
  starts_at: string;
  ends_at: string;
  reason: string;
  created_by: string | null;
  created_at: string;
  cancelled_at: string | null;
}

export interface MaintenanceWindow {
  id: string;
  scope: { servers?: string[]; projects?: string[] };
  starts_at: string;
  ends_at: string;
  reason: string;
  created_by: string | null;
  cancelled_at: string | null;
}

export interface NotificationChannel {
  id: string;
  type: string;
  name: string;
  min_severity: string;
  quiet_hours: unknown;
  is_default: boolean;
  enabled: boolean;
  last_ok_at: string | null;
  last_error: string;
  config_masked: { bot_token?: string; chat_id?: string | number | null; error?: string };
}

export interface AlertRule {
  id: string;
  key: string;
  name: string;
  description: string;
  scope: { type?: string } & Record<string, unknown>;
  condition: unknown;
  for_seconds: number;
  resolve_after_seconds: number;
  severity: string;
  channels: unknown;
  runbook_key: string;
  runbook_hint: string;
  enabled: boolean;
  built_in: boolean;
  updated_at: string;
}

export interface IncidentPage {
  items: Incident[];
  next_before: string | null;
}
