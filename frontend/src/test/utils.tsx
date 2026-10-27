import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import type { Incident, Me, Server } from "../api/types";

export interface MockReply {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}
export type Handler = MockReply | ((url: URL, init: RequestInit) => MockReply);

export interface FetchMock {
  calls: { url: URL; init: RequestInit }[];
}

/** `fetch` ni almashtiradi. Kalit: "METHOD /yo'l" (so'rov satrisiz). Topilmasa 404. */
export function mockFetch(routes: Record<string, Handler>): FetchMock {
  const mock: FetchMock = { calls: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = new URL(typeof input === "string" ? input : input.toString(), "http://localhost");
      mock.calls.push({ url, init });
      const key = `${(init.method ?? "GET").toUpperCase()} ${url.pathname}`;
      const h = routes[key];
      const reply: MockReply = h === undefined ? { status: 404, body: { error: { code: "not_found", message: "Topilmadi." } } } : typeof h === "function" ? h(url, init) : h;
      const status = reply.status ?? 200;
      const headers = new Headers({ "Content-Type": "application/json", ...reply.headers });
      return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), { status, headers });
    }),
  );
  return mock;
}

export function apiError(status: number, code: string, message: string, extra: Partial<MockReply> = {}): MockReply {
  return { status, body: { error: { code, message, details: [], request_id: "req-12345678" } }, ...extra };
}

export const ME: Me = { id: "u1", login: "egasi", role: "owner", language: "uz", timezone: "Asia/Tashkent", mfa_enabled: false };

export function makeClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } } });
}

/** Sahifani Layout konteksti (`useOutletContext`) bilan chizadi. */
export function renderPage(ui: ReactElement, opts: { path?: string; route?: string; me?: Me; client?: QueryClient } = {}) {
  const client = opts.client ?? makeClient();
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[opts.route ?? opts.path ?? "/"]}>
        <Routes>
          <Route element={<OutletProvider me={opts.me ?? ME} />}>
            <Route path={opts.path ?? "/"} element={ui} />
          </Route>
          <Route path="/login" element={<p>login sahifasi</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

function OutletProvider({ me }: { me: Me }) {
  return <Outlet context={me} />;
}

export function server(over: Partial<Server> = {}): Server {
  return {
    id: "s1",
    name: "main-2",
    provider: "Contabo",
    public_ipv4: "164.68.105.194",
    public_ipv6: null,
    role: "",
    tags: ["prod"],
    location: "",
    monthly_cost_usd: null,
    notes: "",
    status: "online",
    last_seen_at: new Date().toISOString(),
    paused_at: null,
    paused_until: null,
    pause_reason: "",
    agent_version: "1.0.0",
    facts: {},
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...over,
  };
}

export function incident(over: Partial<Incident> = {}): Incident {
  return {
    id: "i1",
    scope_key: "host:s1",
    title: "Disk 7 kunda to'ladi",
    severity: "warning",
    status: "open",
    started_at: new Date(Date.now() - 40 * 60_000).toISOString(),
    acked_at: null,
    acked_by: null,
    resolved_at: null,
    suppressed: false,
    root_cause: "",
    summary: {},
    ...over,
  };
}
