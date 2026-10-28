import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Cert, Domain, Probe } from "../api/types";
import { apiError, mockFetch, renderPage } from "../test/utils";
import DomainPage from "./DomainPage";
import DomainsPage from "./DomainsPage";

function domain(over: Partial<Domain> = {}): Domain {
  return {
    id: "d1",
    project: "p1",
    project_slug: "nazar",
    fqdn: "nazar.avlo.ai",
    expected_ips: ["164.68.105.194"],
    dns_provider: "Cloudflare",
    registrar: "",
    controlled_by: "biz",
    tls_enabled: true,
    status: "active",
    notes: "",
    created_at: "2026-10-01T00:00:00Z",
    ...over,
  };
}

function probe(over: Partial<Probe> = {}): Probe {
  return {
    id: "pr1",
    project: "p1",
    domain: "d1",
    type: "http",
    name: "HTTP nazar",
    config: {},
    interval_s: 60,
    timeout_s: 10,
    enabled: true,
    state: "up",
    state_since: null,
    consecutive_failures: 0,
    last_run_at: new Date().toISOString(),
    next_run_at: null,
    created_at: "2026-10-01T00:00:00Z",
    last_result: { time: new Date().toISOString(), ok: true, status_code: 200, total_ms: 120, error_kind: null, detail: {} },
    ...over,
  };
}

function cert(over: Partial<Cert> = {}): Cert {
  return {
    id: 1,
    name: "nazar.avlo.ai",
    source: "probe",
    domain: "d1",
    project: "p1",
    not_after: "2026-12-01T00:00:00Z",
    days_left: 41,
    issuer: "R3",
    subject: "nazar.avlo.ai",
    san: [],
    chain_ok: true,
    hostname_ok: true,
    checked_at: new Date().toISOString(),
    ...over,
  };
}

const lutfan = domain({ id: "d2", fqdn: "lutfanai.uz", project_slug: "lutfan_ai" });

function base(extra: Parameters<typeof mockFetch>[0] = {}) {
  return mockFetch({
    "GET /api/v1/domains/": { body: { items: [domain(), lutfan] } },
    "GET /api/v1/probes/": {
      body: { items: [probe(), probe({ id: "pr2", domain: "d2", state: "down", last_result: null }), probe({ id: "pr3", domain: "d2", type: "dns", state: "down" })] },
    },
    "GET /api/v1/certs/": { body: { items: [cert(), cert({ id: 2, domain: "d2", days_left: 5 })] } },
    ...extra,
  });
}

describe("DomainsPage", () => {
  it("HTTP, sertifikat va DNS holatini domen bo'yicha ko'rsatadi", async () => {
    base();
    renderPage(<DomainsPage />, { path: "/domains" });
    const rows = await screen.findAllByTestId("domain-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("nazar.avlo.ai")).toBeInTheDocument();
    expect(await within(rows[0]!).findByText(/Ishlayapti · 200/)).toBeInTheDocument();
    expect(within(rows[0]!).getByText("41 kun")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("5 kun")).toBeInTheDocument();
  });

  it("'DNS muammolari' filtri faqat muammoli domenni qoldiradi", async () => {
    base();
    renderPage(<DomainsPage />, { path: "/domains" });
    await screen.findAllByTestId("domain-row");
    await screen.findByText(/Ishlayapti · 200/);
    await userEvent.click(screen.getByLabelText("DNS muammolari"));
    const rows = screen.getAllByTestId("domain-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]!).getByText("lutfanai.uz")).toBeInTheDocument();
  });

  it("'Muddati yaqin' filtri 21 kundan kam qolganlarni ko'rsatadi", async () => {
    base();
    renderPage(<DomainsPage />, { path: "/domains" });
    await screen.findAllByTestId("domain-row");
    await screen.findByText("5 kun");
    await userEvent.click(screen.getByLabelText("Muddati yaqin"));
    expect(screen.getAllByTestId("domain-row")).toHaveLength(1);
  });

  it("domen yo'q bo'lsa bo'sh holat ko'rsatadi", async () => {
    base({ "GET /api/v1/domains/": { body: { items: [] } } });
    renderPage(<DomainsPage />, { path: "/domains" });
    expect(await screen.findByText("Hali domen qo'shilmagan")).toBeInTheDocument();
  });

  it("domenlar xatosida xato holatini ko'rsatadi", async () => {
    base({ "GET /api/v1/domains/": apiError(500, "internal", "Ichki xato.") });
    renderPage(<DomainsPage />, { path: "/domains" });
    expect(await screen.findByText("Domenlarni yuklab bo'lmadi")).toBeInTheDocument();
  });
});

describe("DomainPage", () => {
  it("DNS javoblari, o'zgarishlar va kesib o'tish yordamchisi holatini ko'rsatadi", async () => {
    base({
      "GET /api/v1/domains/d1": { body: domain() },
      "GET /api/v1/domains/d1/dns": {
        body: {
          resolvers: [
            { resolver: "Google 8.8.8.8", rtype: "A", time: new Date().toISOString(), answers: ["164.68.105.194"], matches: true, rcode: 0, latency_ms: 12 },
            { resolver: "Quad9 9.9.9.9", rtype: "A", time: new Date().toISOString(), answers: ["34.173.220.247"], matches: false, rcode: 0, latency_ms: 20 },
          ],
          changes: [{ resolver: "Google 8.8.8.8", rtype: "A", old_answers: ["34.173.220.247"], new_answers: ["164.68.105.194"], changed_at: "2026-10-20T10:00:00Z" }],
        },
      },
    });
    renderPage(<DomainPage />, { path: "/domains/:id", route: "/domains/d1" });
    expect(await screen.findByRole("heading", { level: 1, name: "nazar.avlo.ai" })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /DNS javoblari/ });
    expect(within(table).getByText("Mos")).toBeInTheDocument();
    expect(within(table).getByText("Mos emas")).toBeInTheDocument();
    expect(screen.getByText("Kesib o'tish yordamchisi")).toBeInTheDocument();
    expect(await screen.findByText("41 kun")).toBeInTheDocument();
  });

  it("DNS natijasi yo'q bo'lsa tushuntiradi", async () => {
    base({
      "GET /api/v1/domains/d1": { body: domain() },
      "GET /api/v1/domains/d1/dns": { body: { resolvers: [], changes: [] } },
    });
    renderPage(<DomainPage />, { path: "/domains/:id", route: "/domains/d1" });
    expect(await screen.findByText(/Hali DNS tekshiruvi natijasi yo'q/)).toBeInTheDocument();
    expect(screen.getByText("O'zgarish qayd etilmagan.")).toBeInTheDocument();
  });

  it("404 da 'Domen topilmadi' ko'rsatadi", async () => {
    base({ "GET /api/v1/domains/yoq": apiError(404, "not_found", "Domen topilmadi."), "GET /api/v1/domains/yoq/dns": apiError(404, "not_found", "Domen topilmadi.") });
    renderPage(<DomainPage />, { path: "/domains/:id", route: "/domains/yoq" });
    expect(await screen.findByText("Domen topilmadi")).toBeInTheDocument();
  });
});
