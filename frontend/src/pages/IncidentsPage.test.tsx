import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { IncidentDetail } from "../api/types";
import { apiError, incident, ME, mockFetch, renderPage, server } from "../test/utils";
import IncidentPage from "./IncidentPage";
import IncidentsPage from "./IncidentsPage";

beforeEach(() => {
  document.cookie = "csrftoken=tok; path=/";
});

const servers = { "GET /api/v1/servers/": { body: { items: [server()] } } };

describe("IncidentsPage", () => {
  it("incidentlarni holat va server nomi bilan ro'yxatlaydi", async () => {
    mockFetch({
      ...servers,
      "GET /api/v1/incidents/": { body: { items: [incident(), incident({ id: "i2", title: "Sayt ishlamayapti", status: "resolved", severity: "critical" })], next_before: null } },
    });
    renderPage(<IncidentsPage />, { path: "/incidents" });
    const rows = await screen.findAllByTestId("incident-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[1]!).getByText("Hal qilingan")).toBeInTheDocument();
    expect((await screen.findAllByText("main-2")).length).toBe(2);
  });

  it("filtrni so'rovga uzatadi", async () => {
    const m = mockFetch({ ...servers, "GET /api/v1/incidents/": { body: { items: [], next_before: null } } });
    renderPage(<IncidentsPage />, { path: "/incidents", route: "/incidents?status=open&severity=critical" });
    await screen.findByText("Hech narsa topilmadi");
    const call = m.calls.find((c) => c.url.pathname === "/api/v1/incidents/")!;
    expect(call.url.searchParams.get("status")).toBe("open");
    expect(call.url.searchParams.get("severity")).toBe("critical");
  });

  it("'Qabul qilaman' ack so'rovini yuboradi", async () => {
    const m = mockFetch({
      ...servers,
      "GET /api/v1/incidents/": { body: { items: [incident()], next_before: null } },
      "POST /api/v1/incidents/i1/ack": { body: incident({ status: "acknowledged" }) },
    });
    renderPage(<IncidentsPage />, { path: "/incidents" });
    await userEvent.click(await screen.findByRole("button", { name: "Qabul qilaman" }));
    await waitFor(() => expect(m.calls.some((c) => c.init.method === "POST" && c.url.pathname === "/api/v1/incidents/i1/ack")).toBe(true));
  });

  it("kuzatuvchi uchun 'Qabul qilaman' yo'q", async () => {
    mockFetch({ ...servers, "GET /api/v1/incidents/": { body: { items: [incident()], next_before: null } } });
    renderPage(<IncidentsPage />, { path: "/incidents", me: { ...ME, role: "viewer" } });
    await screen.findByTestId("incident-row");
    expect(screen.queryByRole("button", { name: "Qabul qilaman" })).not.toBeInTheDocument();
  });

  it("bo'sh va xato holatlari", async () => {
    mockFetch({ ...servers, "GET /api/v1/incidents/": { body: { items: [], next_before: null } } });
    const { unmount } = renderPage(<IncidentsPage />, { path: "/incidents" });
    expect(await screen.findByText("Incident yo'q")).toBeInTheDocument();
    unmount();
    mockFetch({ ...servers, "GET /api/v1/incidents/": apiError(500, "internal", "Ichki xato.") });
    renderPage(<IncidentsPage />, { path: "/incidents" });
    expect(await screen.findByText("Incidentlarni yuklab bo'lmadi")).toBeInTheDocument();
  });
});

describe("IncidentPage", () => {
  const detail: IncidentDetail = {
    ...incident(),
    alerts: [],
    events: [
      { id: 1, time: "2026-10-28T09:33:00Z", type: "opened", user: null, data: { alert: "AL-001" } },
      { id: 2, time: "2026-10-28T09:41:00Z", type: "comment", user: "jasur", data: { text: "restart berdim" } },
    ],
  };

  it("vaqt chizig'ini ko'rsatadi va izoh yuboradi", async () => {
    const m = mockFetch({
      ...servers,
      "GET /api/v1/incidents/i1": { body: detail },
      "POST /api/v1/incidents/i1/comments": { status: 201, body: {} },
    });
    renderPage(<IncidentPage />, { path: "/incidents/:id", route: "/incidents/i1" });
    expect(await screen.findByRole("heading", { level: 1, name: "Disk 7 kunda to'ladi" })).toBeInTheDocument();
    expect(screen.getByText("Ochildi: AL-001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Qo'shish" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Izoh matni"), "tekshirdim");
    await userEvent.click(screen.getByRole("button", { name: "Qo'shish" }));
    await waitFor(() => {
      const post = m.calls.find((c) => c.url.pathname === "/api/v1/incidents/i1/comments");
      expect(JSON.parse(post!.init.body as string)).toEqual({ text: "tekshirdim" });
    });
  });

  it("qo'lda yopish tasdiq so'raydi", async () => {
    const m = mockFetch({
      ...servers,
      "GET /api/v1/incidents/i1": { body: detail },
      "POST /api/v1/incidents/i1/resolve": { body: incident({ status: "resolved" }) },
    });
    renderPage(<IncidentPage />, { path: "/incidents/:id", route: "/incidents/i1" });
    await userEvent.click(await screen.findByRole("button", { name: "Qo'lda yopish" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(m.calls.some((c) => c.init.method === "POST")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Yopish" }));
    await waitFor(() => expect(m.calls.some((c) => c.url.pathname === "/api/v1/incidents/i1/resolve")).toBe(true));
  });

  it("kuzatuvchi izoh yoza olmaydi", async () => {
    mockFetch({ ...servers, "GET /api/v1/incidents/i1": { body: detail } });
    renderPage(<IncidentPage />, { path: "/incidents/:id", route: "/incidents/i1", me: { ...ME, role: "viewer" } });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByLabelText("Izoh matni")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Qo'lda yopish" })).not.toBeInTheDocument();
  });

  it("404 da 'Incident topilmadi' ko'rsatadi", async () => {
    mockFetch({ ...servers, "GET /api/v1/incidents/x": apiError(404, "not_found", "Incident topilmadi.") });
    renderPage(<IncidentPage />, { path: "/incidents/:id", route: "/incidents/x" });
    expect(await screen.findByText("Incident topilmadi")).toBeInTheDocument();
  });
});
