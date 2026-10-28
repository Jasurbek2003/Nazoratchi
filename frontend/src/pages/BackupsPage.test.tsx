import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BackupDetail, BackupItem, Drill } from "../api/types";
import { apiError, ME, mockFetch, renderPage } from "../test/utils";
import BackupPage from "./BackupPage";
import BackupsPage from "./BackupsPage";

function item(over: Partial<BackupItem> = {}): BackupItem {
  return {
    project: "biznesradar",
    project_id: "p1",
    name: "BiznesRadar",
    server: "main-2",
    server_id: "s1",
    expect_daily: true,
    expect_weekly_files: false,
    require_offsite: true,
    state: "ok",
    age_hours: 6,
    last_success_at: new Date().toISOString(),
    last_size_bytes: 48 * 1024 * 1024,
    last_status: "ok",
    daily_count: 7,
    weekly_count: 2,
    files_count: 0,
    newest_age_seconds: {},
    offsite_configured: false,
    data_seen_at: null,
    drill: { every_days: 90, last: null, last_success_days: null, never: true, overdue: true },
    ...over,
  };
}

describe("BackupsPage", () => {
  it("jadvalni holat, yosh, hajm va offsite bilan chizadi", async () => {
    mockFetch({ "GET /api/v1/backups/": { body: { items: [item(), item({ project: "nazar", project_id: "p2", name: "Nazar", state: "late", age_hours: 31, offsite_configured: true })] } } });
    renderPage(<BackupsPage />, { path: "/backups" });
    const rows = await screen.findAllByTestId("backup-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("BiznesRadar")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("6 soat oldin")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("48 MB")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Sozlanmagan")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Kechikdi")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Sozlangan")).toBeInTheDocument();
  });

  it("'Faqat muammolilar' filtri joyidagilarni yashiradi", async () => {
    mockFetch({ "GET /api/v1/backups/": { body: { items: [item(), item({ project: "nazar", project_id: "p2", name: "Nazar", state: "failed" })] } } });
    renderPage(<BackupsPage />, { path: "/backups" });
    await screen.findAllByTestId("backup-row");
    await userEvent.click(screen.getByLabelText("Faqat muammolilar"));
    const rows = screen.getAllByTestId("backup-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]!).getByText("Nazar")).toBeInTheDocument();
  });

  it("bo'sh ro'yxatda tushuntirish ko'rsatadi", async () => {
    mockFetch({ "GET /api/v1/backups/": { body: { items: [] } } });
    renderPage(<BackupsPage />, { path: "/backups" });
    expect(await screen.findByText("Zaxira kuzatuvi sozlanmagan")).toBeInTheDocument();
  });

  it("xatoda 'Qayta urinish' bilan xato holatini ko'rsatadi", async () => {
    mockFetch({ "GET /api/v1/backups/": apiError(500, "internal", "Ichki xato.") });
    renderPage(<BackupsPage />, { path: "/backups" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Zaxiralarni yuklab bo'lmadi");
    expect(screen.getByRole("button", { name: "Qayta urinish" })).toBeInTheDocument();
  });
});

describe("BackupPage", () => {
  it("kartada hajm grafigi, anomaliya ogohlantirishi va ishlar jadvalini ko'rsatadi", async () => {
    const detail: BackupDetail = {
      ...item(),
      runs: [
        { finished_at: "2026-10-26T02:00:00Z", size_bytes: 40 * 1024 * 1024 },
        { finished_at: "2026-10-27T02:00:00Z", size_bytes: 2 * 1024 * 1024 },
      ],
      size_median_7: 40 * 1024 * 1024,
      size_ratio: 0.05,
      size_anomaly: true,
      drills: [],
    };
    mockFetch({ "GET /api/v1/backups/biznesradar": { body: detail } });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/biznesradar" });
    expect(await screen.findByRole("heading", { level: 1, name: "BiznesRadar" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /zaxira hajmi/ })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Hajm odatdagidan keskin farq qiladi");
    expect(screen.getByRole("table", { name: "Zaxira ishlari" })).toBeInTheDocument();
  });

  it("404 da 'Loyiha topilmadi' holatini ko'rsatadi", async () => {
    mockFetch({ "GET /api/v1/backups/yoq": apiError(404, "not_found", "Loyiha topilmadi.") });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/yoq" });
    expect(await screen.findByText("Loyiha topilmadi")).toBeInTheDocument();
  });
});

function drillRow(over: Partial<Drill> = {}): Drill {
  return {
    id: "d1",
    project: "biznesradar",
    performed_at: "2026-10-20T10:00:00Z",
    performed_by: "egasi",
    backup_file: "BiznesRadar-20261019-031501.sql.gz",
    backup_age_h: 7,
    duration_s: 860,
    tables_count: 42,
    rows_count: 1250000,
    result: "success",
    notes: "",
    ...over,
  };
}

describe("Restore drill", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("hech qachon o'tkazilmagan bo'lsa shuni aniq ko'rsatadi", async () => {
    mockFetch({ "GET /api/v1/backups/biznesradar": { body: { ...item(), runs: [], size_median_7: null, size_ratio: null, size_anomaly: false, drills: [] } } });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/biznesradar" });
    expect(await screen.findByText("Drill: hech qachon")).toBeInTheDocument();
    expect(screen.getByText("Hali drill o'tkazilmagan.")).toBeInTheDocument();
  });

  it("tarixni davomiylik va natija bilan chizadi", async () => {
    const drill = { every_days: 90, last: drillRow(), last_success_days: 8, never: false, overdue: false };
    mockFetch({ "GET /api/v1/backups/biznesradar": { body: { ...item({ drill }), runs: [], size_median_7: null, size_ratio: null, size_anomaly: false, drills: [drillRow()] } } });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/biznesradar" });
    const row = await screen.findByTestId("drill-row");
    expect(within(row).getByText("Muvaffaqiyatli")).toBeInTheDocument();
    expect(within(row).getByText("14 daq 20 s")).toBeInTheDocument();
    expect(screen.getByText("Drill: 8 kun oldin")).toBeInTheDocument();
  });

  it("formani yuboradi va tanani to'g'ri shakllantiradi", async () => {
    const mock = mockFetch({
      "GET /api/v1/backups/biznesradar": { body: { ...item(), runs: [], size_median_7: null, size_ratio: null, size_anomaly: false, drills: [] } },
      "POST /api/v1/backups/drills": { status: 201, body: drillRow() },
    });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/biznesradar" });
    await userEvent.click(await screen.findByRole("button", { name: "Drill natijasini kiritish" }));
    await userEvent.type(screen.getByLabelText("Tiklangan zaxira fayli"), "BiznesRadar-1.sql.gz");
    await userEvent.type(screen.getByLabelText("Davomiylik (soniya)"), "840");
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    const post = await vi.waitFor(() => {
      const c = mock.calls.find((x) => x.init.method === "POST");
      if (!c) throw new Error("POST yo'q");
      return c;
    });
    const body = JSON.parse(String(post.init.body));
    expect(body).toMatchObject({ project: "biznesradar", backup_file: "BiznesRadar-1.sql.gz", duration_s: 840, result: "success", tables_count: null });
  });

  it("fayl nomisiz yubormaydi va xatoni ko'rsatadi", async () => {
    const mock = mockFetch({ "GET /api/v1/backups/biznesradar": { body: { ...item(), runs: [], size_median_7: null, size_ratio: null, size_anomaly: false, drills: [] } } });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/biznesradar" });
    await userEvent.click(await screen.findByRole("button", { name: "Drill natijasini kiritish" }));
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    expect(await screen.findByText("Zaxira fayli nomini kiriting.")).toBeInTheDocument();
    expect(mock.calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("viewer uchun kiritish tugmasi yo'q", async () => {
    mockFetch({ "GET /api/v1/backups/biznesradar": { body: { ...item(), runs: [], size_median_7: null, size_ratio: null, size_anomaly: false, drills: [] } } });
    renderPage(<BackupPage />, { path: "/backups/:slug", route: "/backups/biznesradar", me: { ...ME, role: "viewer" } });
    await screen.findByText("Drill: hech qachon");
    expect(screen.queryByRole("button", { name: "Drill natijasini kiritish" })).not.toBeInTheDocument();
  });
});
