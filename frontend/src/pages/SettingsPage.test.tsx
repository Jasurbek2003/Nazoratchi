import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { AlertRule, NotificationChannel } from "../api/types";
import { apiError, ME, mockFetch, renderPage } from "../test/utils";
import SettingsPage, { channelSchema } from "./SettingsPage";

beforeEach(() => {
  document.cookie = "csrftoken=tok; path=/";
});

const TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_0123456789";

const channel: NotificationChannel = {
  id: "c1",
  type: "telegram",
  name: "Asosiy",
  min_severity: "warning",
  quiet_hours: null,
  is_default: true,
  enabled: true,
  last_ok_at: null,
  last_error: "",
  config_masked: { bot_token: "••••", chat_id: -1001234567 },
};
const rule: AlertRule = {
  id: "r1",
  key: "AL-001",
  name: "Server o'chdi",
  description: "Agent 3 daqiqa jim",
  scope: { type: "host" },
  condition: {},
  for_seconds: 180,
  resolve_after_seconds: 60,
  severity: "critical",
  channels: [],
  runbook_key: "",
  runbook_hint: "",
  enabled: true,
  built_in: true,
  updated_at: "2026-10-01T00:00:00Z",
};

describe("channelSchema", () => {
  const ok = { name: "A", min_severity: "warning", bot_token: TOKEN, chat_id: "-1001234567" };
  it("to'g'ri qiymatlarni qabul qiladi", () => {
    expect(channelSchema.safeParse(ok).success).toBe(true);
    expect(channelSchema.safeParse({ ...ok, chat_id: "@nazoratchi_alert" }).success).toBe(true);
  });
  it("noto'g'ri token va chat ID ni rad etadi", () => {
    expect(channelSchema.safeParse({ ...ok, bot_token: "abc" }).success).toBe(false);
    expect(channelSchema.safeParse({ ...ok, chat_id: "salom" }).success).toBe(false);
  });
});

describe("SettingsPage: kanallar", () => {
  it("kanalni sirsiz ko'rsatadi", async () => {
    mockFetch({ "GET /api/v1/channels/": { body: { items: [channel] } } });
    renderPage(<SettingsPage />, { path: "/settings" });
    const row = await screen.findByTestId("channel-row");
    expect(row).toHaveTextContent("Asosiy");
    expect(row).toHaveTextContent("-1001234567");
    expect(row).toHaveTextContent("Token: yashirin");
    expect(row.textContent).not.toContain("••••");
  });

  it("noto'g'ri token bilan tarmoqqa chiqmaydi", async () => {
    const m = mockFetch({ "GET /api/v1/channels/": { body: { items: [] } } });
    renderPage(<SettingsPage />, { path: "/settings" });
    await userEvent.click(await screen.findByRole("button", { name: "Telegram kanalini qo'shish" }));
    await userEvent.type(screen.getByLabelText("Nomi"), "Asosiy");
    await userEvent.type(screen.getByLabelText("Bot tokeni"), "xato");
    await userEvent.type(screen.getByLabelText("Chat ID"), "-100123");
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    expect(await screen.findByText(/Token noto'g'ri/)).toBeInTheDocument();
    expect(m.calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("kanal yaratadi: chat_id son sifatida yuboriladi", async () => {
    const m = mockFetch({ "GET /api/v1/channels/": { body: { items: [] } }, "POST /api/v1/channels/": { status: 201, body: channel } });
    renderPage(<SettingsPage />, { path: "/settings" });
    await userEvent.click(await screen.findByRole("button", { name: "Telegram kanalini qo'shish" }));
    await userEvent.type(screen.getByLabelText("Nomi"), "Asosiy");
    await userEvent.type(screen.getByLabelText("Bot tokeni"), TOKEN);
    await userEvent.type(screen.getByLabelText("Chat ID"), "-1001234567");
    await userEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    await waitFor(() => {
      const post = m.calls.find((c) => c.init.method === "POST");
      expect(JSON.parse(post!.init.body as string)).toEqual({ type: "telegram", name: "Asosiy", min_severity: "warning", config: { bot_token: TOKEN, chat_id: -1001234567 } });
    });
  });

  it("sinash: muvaffaqiyat va 502 xatosini ko'rsatadi", async () => {
    mockFetch({ "GET /api/v1/channels/": { body: { items: [channel] } }, "POST /api/v1/channels/c1/test": { body: { ok: true, status: "sent", error: "" } } });
    const { unmount } = renderPage(<SettingsPage />, { path: "/settings" });
    await userEvent.click(await screen.findByRole("button", { name: "Sinash" }));
    expect(await screen.findByText("Sinov xabari yuborildi.")).toBeInTheDocument();
    unmount();
    mockFetch({ "GET /api/v1/channels/": { body: { items: [channel] } }, "POST /api/v1/channels/c1/test": { status: 502, body: { ok: false, status: "failed", error: "chat not found" } } });
    renderPage(<SettingsPage />, { path: "/settings" });
    await userEvent.click(await screen.findByRole("button", { name: "Sinash" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sinov xabari yuborilmadi");
  });

  it("o'chirish tasdiq so'raydi", async () => {
    const m = mockFetch({ "GET /api/v1/channels/": { body: { items: [channel] } }, "DELETE /api/v1/channels/c1": { status: 204 } });
    renderPage(<SettingsPage />, { path: "/settings" });
    await userEvent.click(await screen.findByRole("button", { name: "O'chirib tashlash" }));
    expect(m.calls.some((c) => c.init.method === "DELETE")).toBe(false);
    const dialog = screen.getByRole("dialog");
    await userEvent.click(screen.getAllByRole("button", { name: "O'chirib tashlash" }).find((b) => dialog.contains(b))!);
    await waitFor(() => expect(m.calls.some((c) => c.init.method === "DELETE")).toBe(true));
  });

  it("egasi bo'lmaganlarga kanallarni so'ramaydi", async () => {
    const m = mockFetch({});
    renderPage(<SettingsPage />, { path: "/settings", me: { ...ME, role: "operator" } });
    expect(await screen.findByText("Kanallarni faqat egasi boshqaradi")).toBeInTheDocument();
    expect(m.calls.some((c) => c.url.pathname === "/api/v1/channels/")).toBe(false);
  });

  it("bo'sh va xato holatlari", async () => {
    mockFetch({ "GET /api/v1/channels/": { body: { items: [] } } });
    const { unmount } = renderPage(<SettingsPage />, { path: "/settings" });
    expect(await screen.findByText("Birinchi bildirishnoma kanalini qo'shing")).toBeInTheDocument();
    unmount();
    mockFetch({ "GET /api/v1/channels/": apiError(500, "internal", "Ichki xato.") });
    renderPage(<SettingsPage />, { path: "/settings" });
    expect(await screen.findByText("Kanallarni yuklab bo'lmadi")).toBeInTheDocument();
  });
});

describe("SettingsPage: qoidalar", () => {
  it("qoidalarni ko'rsatadi va yoqish/o'chirishni PATCH qiladi", async () => {
    const m = mockFetch({ "GET /api/v1/alert-rules/": { body: { items: [rule] } }, "PATCH /api/v1/alert-rules/r1": { body: { ...rule, enabled: false } } });
    renderPage(<SettingsPage />, { path: "/settings", route: "/settings?tab=rules" });
    const row = await screen.findByTestId("rule-row");
    expect(row).toHaveTextContent("AL-001");
    expect(row).toHaveTextContent("Server o'chdi");
    await userEvent.click(screen.getByRole("checkbox", { name: "Server o'chdi qoidasi yoqilgan" }));
    await waitFor(() => {
      const patch = m.calls.find((c) => c.init.method === "PATCH");
      expect(JSON.parse(patch!.init.body as string)).toEqual({ enabled: false });
    });
  });

  it("kuzatuvchi uchun faqat o'qish", async () => {
    mockFetch({ "GET /api/v1/alert-rules/": { body: { items: [rule] } } });
    renderPage(<SettingsPage />, { path: "/settings", route: "/settings?tab=rules", me: { ...ME, role: "viewer" } });
    await screen.findByTestId("rule-row");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("bo'sh va xato", async () => {
    mockFetch({ "GET /api/v1/alert-rules/": { body: { items: [] } } });
    const { unmount } = renderPage(<SettingsPage />, { path: "/settings", route: "/settings?tab=rules" });
    expect(await screen.findByText("Alert qoidalari yo'q")).toBeInTheDocument();
    unmount();
    mockFetch({ "GET /api/v1/alert-rules/": apiError(500, "internal", "Ichki xato.") });
    renderPage(<SettingsPage />, { path: "/settings", route: "/settings?tab=rules" });
    expect(await screen.findByText("Qoidalarni yuklab bo'lmadi")).toBeInTheDocument();
  });
});
