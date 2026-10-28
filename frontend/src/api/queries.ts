/** TanStack Query kancalari. staleTime 10 s (ro'yxatlar), 30 s (grafiklar) — TZ 13.8. */
import { keepPreviousData, useInfiniteQuery, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, request } from "./client";
import type {
  AlertInstance,
  AlertRule,
  BackupDetail,
  BackupItem,
  DnsInfo,
  Domain,
  IncidentPage,
  MaintenanceWindow,
  Matcher,
  NotificationChannel,
  Silence,
  Cert,
  Container,
  Filesystem,
  Incident,
  IncidentDetail,
  LatestResponse,
  Me,
  Probe,
  Project,
  QueryResponse,
  Server,
  ServerDetail,
  ServerEnvelope,
} from "./types";

export const LIST_STALE_MS = 10_000;
export const CHART_STALE_MS = 30_000;
/** SSE hozircha yo'q: jonli yangilanish polling bilan. */
export const POLL_MS = 10_000;

export const keys = {
  me: ["me"] as const,
  servers: (params?: object) => ["servers", params ?? {}] as const,
  server: (id: string) => ["server", id] as const,
  incidents: (status: string) => ["incidents", status] as const,
  incident: (id: string) => ["incident", id] as const,
  alerts: ["alerts"] as const,
  latest: (serverId: string) => ["latest", serverId] as const,
  spark: (serverId: string) => ["spark", serverId] as const,
  metric: (serverId: string, name: string, range: string) => ["metric", serverId, name, range] as const,
  containers: (id: string) => ["containers", id] as const,
  filesystems: (id: string) => ["filesystems", id] as const,
  projects: (params?: object) => ["projects", params ?? {}] as const,
  project: (id: string) => ["project", id] as const,
  probes: (projectId?: string) => ["probes", projectId ?? "all"] as const,
  certs: (params?: object) => ["certs", params ?? {}] as const,
};

// ------------------------------------------------------------------ auth
export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await request<Me>("GET", "auth/me", { quiet401: true });
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("auth/logout"),
    onSettled: () => {
      qc.setQueryData(keys.me, null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
  });
}

// ------------------------------------------------------------------ serverlar
export function useServers() {
  return useQuery({
    queryKey: keys.servers(),
    queryFn: async () => (await api.get<ServerEnvelope<Server>>("servers/")).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  });
}

export function useServer(id: string) {
  return useQuery({
    queryKey: keys.server(id),
    queryFn: () => api.get<ServerDetail>(`servers/${id}`),
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  });
}

export const LATEST_NAMES = [
  "cpu_busy_percent",
  "mem_used_percent",
  "fs_used_percent",
  "load1",
  "net_rx_bytes_per_sec",
  "net_tx_bytes_per_sec",
] as const;

export function latestOptions(serverId: string) {
  return {
    queryKey: keys.latest(serverId),
    queryFn: () => api.get<LatestResponse>("metrics/latest", { server_id: serverId, names: LATEST_NAMES.join(",") }),
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  };
}

export function useLatest(serverId: string, enabled = true) {
  return useQuery({ ...latestOptions(serverId), enabled });
}

/** Ko'p server uchun parallel (TanStack Query keshlaydi). */
export function useLatestMany(serverIds: string[]) {
  return useQueries({ queries: serverIds.map((id) => latestOptions(id)) });
}

export function sparkOptions(serverId: string) {
  return {
    queryKey: keys.spark(serverId),
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - 3600_000);
      return api.get<QueryResponse>("metrics/query", {
        server_id: serverId,
        name: "cpu_busy_percent",
        from: from.toISOString(),
        to: to.toISOString(),
        max_points: 100,
      });
    },
    staleTime: CHART_STALE_MS,
    refetchInterval: 60_000,
  };
}

export function useSpark(serverId: string, enabled = true) {
  return useQuery({ ...sparkOptions(serverId), enabled });
}

export interface RangeSpec {
  key: string;
  label: string;
  aria: string;
  seconds: number;
}

export const RANGES: RangeSpec[] = [
  { key: "1h", label: "1s", aria: "1 soat", seconds: 3600 },
  { key: "6h", label: "6s", aria: "6 soat", seconds: 6 * 3600 },
  { key: "24h", label: "24s", aria: "24 soat", seconds: 24 * 3600 },
  { key: "7d", label: "7k", aria: "7 kun", seconds: 7 * 86400 },
];

export function useMetric(serverId: string, name: string, rangeKey: string) {
  const range = RANGES.find((r) => r.key === rangeKey) ?? RANGES[0]!;
  return useQuery({
    queryKey: keys.metric(serverId, name, range.key),
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - range.seconds * 1000);
      return api.get<QueryResponse>("metrics/query", {
        server_id: serverId,
        name,
        from: from.toISOString(),
        to: to.toISOString(),
        max_points: 600,
      });
    },
    staleTime: CHART_STALE_MS,
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useContainers(id: string) {
  return useQuery({
    queryKey: keys.containers(id),
    queryFn: async () => (await api.get<ServerEnvelope<Container>>(`servers/${id}/containers`)).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  });
}

export function useFilesystems(id: string) {
  return useQuery({
    queryKey: keys.filesystems(id),
    queryFn: async () => (await api.get<ServerEnvelope<Filesystem>>(`servers/${id}/filesystems`)).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  });
}

export function useServerAction(id: string, action: "pause" | "resume") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: { reason: string; until?: string }) => api.post<Server>(`servers/${id}/${action}`, body ?? {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.server(id) });
      void qc.invalidateQueries({ queryKey: ["servers"] });
    },
  });
}

// ------------------------------------------------------------------ incident va alertlar
/** Ochiq = open + acknowledged (hal qilinmagan). Ikkita so'rov (backend `status` bitta qiymat oladi). */
export function useUnresolvedIncidents() {
  const results = useQueries({
    queries: (["open", "acknowledged"] as const).map((status) => ({
      queryKey: keys.incidents(status),
      queryFn: async () => (await api.get<ServerEnvelope<Incident>>("incidents/", { status })).items,
      staleTime: LIST_STALE_MS,
      refetchInterval: POLL_MS,
    })),
  });
  const loading = results.some((r) => r.isPending);
  const error = results.find((r) => r.error)?.error ?? null;
  const data = results.every((r) => r.data) ? results.flatMap((r) => r.data ?? []) : undefined;
  const updatedAt = Math.min(...results.map((r) => r.dataUpdatedAt || Infinity));
  return {
    data,
    isPending: loading,
    error: error as Error | null,
    dataUpdatedAt: Number.isFinite(updatedAt) ? updatedAt : 0,
    refetch: () => Promise.all(results.map((r) => r.refetch())),
  };
}

export function useIncidentDetail(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.incident(id),
    queryFn: () => api.get<IncidentDetail>(`incidents/${id}`),
    enabled,
    staleTime: LIST_STALE_MS,
  });
}

export function useAckIncident() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Incident>(`incidents/${id}/ack`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["incidents"] });
      void qc.invalidateQueries({ queryKey: ["incident"] });
    },
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: keys.alerts,
    queryFn: async () => (await api.get<ServerEnvelope<AlertInstance>>("alerts/")).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  });
}

// ------------------------------------------------------------------ loyihalar
export function useProjects(status: "active" | "archived") {
  return useQuery({
    queryKey: keys.projects({ status }),
    queryFn: async () => (await api.get<ServerEnvelope<Project>>("projects/", { status })).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS * 3,
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: keys.project(id),
    queryFn: () => api.get<Project>(`projects/${id}`),
    staleTime: LIST_STALE_MS,
  });
}

export function useProbes(projectId?: string) {
  return useQuery({
    queryKey: keys.probes(projectId),
    queryFn: async () => (await api.get<ServerEnvelope<Probe>>("probes/", { project_id: projectId })).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS * 3,
  });
}

export function useCerts(params: { days_left_lt?: number; project_id?: string } = {}) {
  return useQuery({
    queryKey: keys.certs(params),
    queryFn: async () => (await api.get<ServerEnvelope<Cert>>("certs/", params)).items,
    staleTime: CHART_STALE_MS,
    refetchInterval: 60_000,
  });
}

/** Bir grafikdagi bir nechta metrika (masalan, load1/5/15) — parallel. */
export function useMetrics(serverId: string, names: string[], rangeKey: string) {
  const range = RANGES.find((r) => r.key === rangeKey) ?? RANGES[0]!;
  return useQueries({
    queries: names.map((name) => ({
      queryKey: keys.metric(serverId, name, range.key),
      queryFn: () => {
        const to = new Date();
        const from = new Date(to.getTime() - range.seconds * 1000);
        return api.get<QueryResponse>("metrics/query", {
          server_id: serverId,
          name,
          from: from.toISOString(),
          to: to.toISOString(),
          max_points: 600,
        });
      },
      staleTime: CHART_STALE_MS,
      refetchInterval: 60_000,
      placeholderData: keepPreviousData,
    })),
  });
}

// ------------------------------------------------------------------ S9: zaxira
export function useBackups() {
  return useQuery({
    queryKey: ["backups"] as const,
    queryFn: async () => (await api.get<ServerEnvelope<BackupItem>>("backups/")).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: 60_000,
  });
}

export function useBackup(slug: string) {
  return useQuery({
    queryKey: ["backup", slug] as const,
    queryFn: () => api.get<BackupDetail>(`backups/${encodeURIComponent(slug)}`),
    staleTime: LIST_STALE_MS,
    refetchInterval: 60_000,
  });
}

// ------------------------------------------------------------------ S9: domenlar
export function useDomains() {
  return useQuery({
    queryKey: ["domains"] as const,
    queryFn: async () => (await api.get<ServerEnvelope<Domain>>("domains/")).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: 60_000,
  });
}

export function useDomain(id: string) {
  return useQuery({
    queryKey: ["domain", id] as const,
    queryFn: () => api.get<Domain>(`domains/${id}`),
    staleTime: LIST_STALE_MS,
  });
}

export function useDomainDns(id: string) {
  return useQuery({
    queryKey: ["domain-dns", id] as const,
    queryFn: () => api.get<DnsInfo>(`domains/${id}/dns`),
    staleTime: LIST_STALE_MS,
    refetchInterval: 60_000,
  });
}

// ------------------------------------------------------------------ S9: incidentlar ro'yxati
/** Tarixiy ro'yxat (hamma holatlar). `next_before` bilan sahifalanadi. */
export function useIncidentList(filter: { status?: string; severity?: string }) {
  return useInfiniteQuery({
    queryKey: ["incidents", "list", filter.status ?? "", filter.severity ?? ""] as const,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.get<IncidentPage>("incidents/", { ...filter, before: pageParam }),
    getNextPageParam: (last) => last.next_before ?? undefined,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS,
  });
}

function invalidateIncidents(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ["incidents"] });
  void qc.invalidateQueries({ queryKey: ["incident"] });
}

export function useIncidentComment(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => api.post<unknown>(`incidents/${id}/comments`, { text }),
    onSuccess: () => invalidateIncidents(qc),
  });
}

export function useResolveIncident(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Incident>(`incidents/${id}/resolve`, {}),
    onSuccess: () => invalidateIncidents(qc),
  });
}

// ------------------------------------------------------------------ S9: silence va texnik ish
export function useSilences() {
  return useQuery({
    queryKey: ["silences"] as const,
    queryFn: async () => (await api.get<ServerEnvelope<Silence>>("silences/")).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS * 3,
  });
}

export function useCreateSilence() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { matchers: Matcher[]; ends_at: string; reason: string }) => api.post<Silence>("silences/", body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["silences"] }),
  });
}

export function useCancelSilence() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => request<void>("DELETE", `silences/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["silences"] }),
  });
}

export function useMaintenance() {
  return useQuery({
    queryKey: ["maintenance"] as const,
    queryFn: async () => (await api.get<ServerEnvelope<MaintenanceWindow>>("maintenance/")).items,
    staleTime: LIST_STALE_MS,
    refetchInterval: POLL_MS * 3,
  });
}

export function useCreateMaintenance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { scope: { servers?: string[]; projects?: string[] }; starts_at: string; ends_at: string; reason: string }) =>
      api.post<MaintenanceWindow>("maintenance/", body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["maintenance"] }),
  });
}

export function useCancelMaintenance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => request<void>("DELETE", `maintenance/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["maintenance"] }),
  });
}

// ------------------------------------------------------------------ S9: sozlamalar
export function useChannels(enabled = true) {
  return useQuery({
    queryKey: ["channels"] as const,
    queryFn: async () => (await api.get<ServerEnvelope<NotificationChannel>>("channels/")).items,
    staleTime: LIST_STALE_MS,
    enabled,
  });
}

export interface ChannelInput {
  type: "telegram";
  name: string;
  min_severity: string;
  config: { bot_token: string; chat_id: string | number };
}

export function useCreateChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ChannelInput) => api.post<NotificationChannel>("channels/", body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}

export function useUpdateChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: string; enabled?: boolean }) => request<NotificationChannel>("PATCH", `channels/${id}`, { body: patch }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}

export function useDeleteChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => request<void>("DELETE", `channels/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}

export function useTestChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<{ ok: boolean; status: string; error: string }>(`channels/${id}/test`, {}),
    // Yuborilmasa backend 502 qaytaradi (xato sifatida keladi); `last_error` yangilanishi uchun doim qayta o'qiymiz.
    onSettled: () => void qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}

export function useAlertRules() {
  return useQuery({
    queryKey: ["alert-rules"] as const,
    queryFn: async () => (await api.get<ServerEnvelope<AlertRule>>("alert-rules/")).items,
    staleTime: LIST_STALE_MS,
  });
}

export function useToggleRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => request<AlertRule>("PATCH", `alert-rules/${id}`, { body: { enabled } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
}
