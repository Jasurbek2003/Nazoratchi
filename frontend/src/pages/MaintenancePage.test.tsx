import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { MaintenanceWindow, Project, Silence } from "../api/types";
import { apiError, ME, mockFetch, renderPage, server } from "../test/utils";
import MaintenancePage from "./MaintenancePage";

beforeEach(() => {
  document.cookie = "csrftoken=tok; path=/";
});

const silence: Silence = {
  id: "sl1",
  matchers: [{ label: "server", op: "=", value: "main-2" }],
  starts_at: "2026-10-28T08:00:00Z",
  ends_at: "2099-10-28T12:00:00Z",
  reason: "Rejali yangilash",
  created_by: "jasur",
  created_at: "2026-10-28T08:00:00Z",
  cancelled_at: null,
};
const win: MaintenanceWindow = {
  id: "mw1",
  scope: { servers: ["s1"] },
  starts_at: "2026-01-01T08:00:00Z",
  ends_at: "2099-10-28T12:00:00Z",
  reason: "OS yangilash",
  created_by: "jasur",
  cancelled_at: null,
};

function base(extra: Parameters<typeof mockFetch>[0] = {}) {
  return mockFetch({
    "GET /api/v1/servers/": { body: { items: [server()] } },
    "GET /api/v1/projects/": { body: { items: [{ id: "p1", name: "Nazar" } as Project] } },
    "GET /api/v1/maintenance/": { body: { items: [win] } },
    "GET /api/v1/silences/": { body: { items: [silence] } },
    ...extra,
  });
}

describe("MaintenancePage", () => {
  it("texnik ish oynalarini server nomi bilan ko'rsatadi", async () => {
    base();
    renderPage(<MaintenancePage />, { path: "/maintenance" });
    const row = await screen.findByTestId("maintenance-row");
    expect(row).toHaveTextContent("OS yangilash");
    await waitFor(() => expect(row).toHaveTextContent("main-2"));
    expect(row).toHaveTextContent("Davom etmoqda");
  });

  it("silence ro'yxati alohida bo'limda", async () => {
    base();
    renderPage(<MaintenancePage />, { path: "/maintenance", route: "/maintenance?tab=silences" });
    const row = await screen.findByTestId("silence-row");
    expect(row).toHaveTextContent("Server = main-2");
    expect(row).toHaveTextContent("Rejali yangilash");
  });

  it("silence formasi bo'sh qiymat va sababni tarmoqqa chiqmasdan rad etadi", async () => {
    const m = base();
    renderPage(<MaintenancePage />, { path: "/maintenance", route: "/maintenance?tab=silences" });
    await userEvent.click(await screen.findByRole("button", { name: "Yangi silence" }));
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    expect(await screen.findByText("Qiymatni kiriting.")).toBeInTheDocument();
    expect(screen.getByText("Sababni yozing.")).toBeInTheDocument();
    expect(m.calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("silence yaratadi: shartlar, muddat va sabab yuboriladi", async () => {
    const m = base({ "POST /api/v1/silences/": { status: 201, body: silence } });
    renderPage(<MaintenancePage />, { path: "/maintenance", route: "/maintenance?tab=silences" });
    await userEvent.click(await screen.findByRole("button", { name: "Yangi silence" }));
    await userEvent.type(screen.getByLabelText("1-shart: qiymat"), "main-2");
    await userEvent.type(screen.getByLabelText("Sabab"), "yangilash");
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    await waitFor(() => {
      const post = m.calls.find((c) => c.init.method === "POST" && c.url.pathname === "/api/v1/silences/");
      expect(post).toBeDefined();
      const body = JSON.parse(post!.init.body as string);
      expect(body.matchers).toEqual([{ label: "server", op: "=", value: "main-2" }]);
      expect(body.reason).toBe("yangilash");
      const mins = (Date.parse(body.ends_at) - Date.now()) / 60_000;
      expect(mins).toBeGreaterThan(235);
      expect(mins).toBeLessThanOrEqual(240);
    });
  });

  it("texnik ish formasi qamrov tanlanmasa rad etadi", async () => {
    const m = base();
    renderPage(<MaintenancePage />, { path: "/maintenance" });
    await userEvent.click(await screen.findByRole("button", { name: "Yangi texnik ish" }));
    await userEvent.type(screen.getByLabelText("Sabab"), "yangilash");
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    expect(await screen.findByText("Kamida bitta server yoki loyihani tanlang.")).toBeInTheDocument();
    expect(m.calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("texnik ish yaratadi", async () => {
    const m = base({ "POST /api/v1/maintenance/": { status: 201, body: win } });
    renderPage(<MaintenancePage />, { path: "/maintenance" });
    await userEvent.click(await screen.findByRole("button", { name: "Yangi texnik ish" }));
    await userEvent.click(await screen.findByLabelText("main-2"));
    await userEvent.type(screen.getByLabelText("Sabab"), "yangilash");
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    await waitFor(() => {
      const post = m.calls.find((c) => c.init.method === "POST" && c.url.pathname === "/api/v1/maintenance/");
      expect(post).toBeDefined();
      expect(JSON.parse(post!.init.body as string).scope).toEqual({ servers: ["s1"] });
    });
  });

  it("bekor qilish tasdiqdan keyin DELETE yuboradi", async () => {
    const m = base({ "DELETE /api/v1/silences/sl1": { status: 204 } });
    renderPage(<MaintenancePage />, { path: "/maintenance", route: "/maintenance?tab=silences" });
    await userEvent.click(await screen.findByRole("button", { name: "Bekor qilish" }));
    expect(m.calls.some((c) => c.init.method === "DELETE")).toBe(false);
    const dialog = screen.getByRole("dialog");
    await userEvent.click(screen.getAllByRole("button", { name: "Bekor qilish" }).find((b) => dialog.contains(b))!);
    await waitFor(() => expect(m.calls.some((c) => c.init.method === "DELETE" && c.url.pathname === "/api/v1/silences/sl1")).toBe(true));
  });

  it("kuzatuvchida yaratish va bekor qilish tugmalari yo'q", async () => {
    base();
    renderPage(<MaintenancePage />, { path: "/maintenance", me: { ...ME, role: "viewer" } });
    await screen.findByTestId("maintenance-row");
    expect(screen.queryByRole("button", { name: "Yangi texnik ish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bekor qilish" })).not.toBeInTheDocument();
  });

  it("bo'sh va xato holatlari", async () => {
    base({ "GET /api/v1/maintenance/": { body: { items: [] } } });
    const { unmount } = renderPage(<MaintenancePage />, { path: "/maintenance" });
    expect(await screen.findByText("Rejalashtirilgan texnik ish yo'q")).toBeInTheDocument();
    unmount();
    base({ "GET /api/v1/maintenance/": apiError(500, "internal", "Ichki xato.") });
    renderPage(<MaintenancePage />, { path: "/maintenance" });
    expect(await screen.findByText("Texnik ishlar ro'yxatini yuklab bo'lmadi")).toBeInTheDocument();
  });
});
