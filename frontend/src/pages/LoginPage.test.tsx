import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import LoginPage, { loginErrorMessage } from "./LoginPage";
import { ApiError } from "../api/client";
import { apiError, ME, makeClient, mockFetch } from "../test/utils";

function setup(routes: Parameters<typeof mockFetch>[0]) {
  document.cookie = "csrftoken=tok; path=/";
  const m = mockFetch({ "GET /api/v1/auth/me": apiError(401, "unauthenticated", "Avval tizimga kiring."), ...routes });
  const client = makeClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>bosh sahifa</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return m;
}

beforeEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("LoginPage", () => {
  it("bo'sh maydonlarda tarmoqqa chiqmasdan, maydon yonida xato ko'rsatadi", async () => {
    const m = setup({});
    await userEvent.click(await screen.findByRole("button", { name: "Kirish" }));
    expect(await screen.findByText("Loginni kiriting.")).toBeInTheDocument();
    expect(screen.getByText("Parolni kiriting.")).toBeInTheDocument();
    expect(m.calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("muvaffaqiyatli kirishda CSRF bilan POST yuboradi va / ga o'tadi", async () => {
    const m = setup({ "POST /api/v1/auth/login": { body: { user: ME } } });
    await userEvent.type(await screen.findByLabelText("Login"), "egasi");
    await userEvent.type(screen.getByLabelText("Parol"), "Kuchli-parol-2026!");
    await userEvent.click(screen.getByRole("button", { name: "Kirish" }));
    expect(await screen.findByText("bosh sahifa")).toBeInTheDocument();
    const post = m.calls.find((c) => c.init.method === "POST")!;
    expect((post.init.headers as Record<string, string>)["X-CSRFToken"]).toBe("tok");
    expect(JSON.parse(post.init.body as string)).toEqual({ login: "egasi", password: "Kuchli-parol-2026!" });
  });

  it("401 da 'noto'g'ri' xabarini ko'rsatadi va sahifada qoladi", async () => {
    setup({ "POST /api/v1/auth/login": apiError(401, "unauthenticated", "Login yoki parol noto'g'ri.") });
    await userEvent.type(await screen.findByLabelText("Login"), "egasi");
    await userEvent.type(screen.getByLabelText("Parol"), "xato");
    await userEvent.click(screen.getByRole("button", { name: "Kirish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Login yoki parol noto'g'ri");
    expect(screen.queryByText("bosh sahifa")).not.toBeInTheDocument();
  });

  it("429 da kutish vaqtini ko'rsatadi", async () => {
    setup({ "POST /api/v1/auth/login": apiError(429, "rate_limited", "So'rovlar juda ko'p.", { headers: { "Retry-After": "45" } }) });
    await userEvent.type(await screen.findByLabelText("Login"), "egasi");
    await userEvent.type(screen.getByLabelText("Parol"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Kirish" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("45 soniyadan keyin"));
  });
});

describe("loginErrorMessage", () => {
  const mk = (status: number, code: string, retryAfter: number | null = null) => new ApiError({ status, code, message: "m", retryAfter });
  it("423 bloklanganda daqiqaga yaxlitlaydi", () => {
    expect(loginErrorMessage(mk(423, "account_locked", 600))).toContain("10 daqiqadan keyin");
    expect(loginErrorMessage(mk(423, "account_locked", 61))).toContain("2 daqiqadan keyin");
  });
  it("tarmoq xatosi va 5xx uchun alohida matn beradi", () => {
    expect(loginErrorMessage(new TypeError("fail"))).toContain("ulanib bo'lmadi");
    expect(loginErrorMessage(mk(503, "x"))).toContain("Server hozir javob bera olmayapti");
  });
  it("csrf_failed uchun sahifani yangilashni aytadi", () => {
    expect(loginErrorMessage(mk(403, "csrf_failed"))).toContain("Sahifani yangilab");
  });
});
