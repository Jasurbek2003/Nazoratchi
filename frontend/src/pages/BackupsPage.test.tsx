import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { BackupDetail, BackupItem } from "../api/types";
import { apiError, mockFetch, renderPage } from "../test/utils";
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
