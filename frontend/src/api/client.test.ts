import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { api, ApiError, buildUrl, ensureCsrf, request, setUnauthorizedHandler } from "./client";
import { apiError, mockFetch } from "../test/utils";

function setCookie(value: string | null) {
  document.cookie = `csrftoken=${value ?? ""}; path=/; ${value === null ? "expires=Thu, 01 Jan 1970 00:00:00 GMT" : ""}`;
}

beforeEach(() => setCookie(null));
afterEach(() => setUnauthorizedHandler(null));

describe("buildUrl", () => {
  it("nisbiy yo'lga /api/v1 qo'shadi va bo'sh qiymatlarni tashlaydi", () => {
    expect(buildUrl("servers/", { q: "a b", tag: undefined, status: "", n: 5 })).toBe("/api/v1/servers/?q=a+b&n=5");
    expect(buildUrl("/healthz")).toBe("/healthz");
  });
});

describe("CSRF", () => {
  it("cookie yo'q bo'lsa GET /auth/csrf chaqiriladi, so'ng yozuvchi so'rovga X-CSRFToken qo'shiladi", async () => {
    const m = mockFetch({
      "GET /api/v1/auth/csrf": () => {
        setCookie("tok123");
        return { status: 204 };
      },
      "POST /api/v1/things": { body: { ok: true } },
    });
    await api.post("things", { a: 1 });
    expect(m.calls.map((c) => `${c.init.method ?? "GET"} ${c.url.pathname}`)).toEqual(["GET /api/v1/auth/csrf", "POST /api/v1/things"]);
    const post = m.calls[1]!;
    expect((post.init.headers as Record<string, string>)["X-CSRFToken"]).toBe("tok123");
    expect(post.init.credentials).toBe("same-origin");
    expect(post.init.body).toBe('{"a":1}');
  });

  it("GET so'rovda CSRF sarlavhasi yuborilmaydi va csrf endpointi chaqirilmaydi", async () => {
    const m = mockFetch({ "GET /api/v1/servers/": { body: { items: [] } } });
    await api.get("servers/");
    expect(m.calls).toHaveLength(1);
    expect((m.calls[0]!.init.headers as Record<string, string>)["X-CSRFToken"]).toBeUndefined();
  });

  it("403 csrf_failed bo'lsa tokenni yangilab, bir marta qayta urinadi", async () => {
    setCookie("old");
    let posts = 0;
    const m = mockFetch({
      "GET /api/v1/auth/csrf": () => {
        setCookie("fresh");
        return { status: 204 };
      },
      "POST /api/v1/things": () => {
        posts += 1;
        return posts === 1 ? apiError(403, "csrf_failed", "CSRF tekshiruvi o'tmadi.") : { body: { done: 1 } };
      },
    });
    await expect(api.post("things", {})).resolves.toEqual({ done: 1 });
    const tokens = m.calls.filter((c) => c.init.method === "POST").map((c) => (c.init.headers as Record<string, string>)["X-CSRFToken"]);
    expect(tokens).toEqual(["old", "fresh"]);
  });

  it("ensureCsrf mavjud cookie'ni qaytaradi (tarmoqsiz)", async () => {
    setCookie("exists");
    const m = mockFetch({});
    await expect(ensureCsrf()).resolves.toBe("exists");
    expect(m.calls).toHaveLength(0);
  });
});

describe("xatolar", () => {
  it("xato formatini ApiError ga aylantiradi (kod, xabar, request_id, Retry-After)", async () => {
    mockFetch({ "GET /api/v1/x": apiError(429, "rate_limited", "So'rovlar juda ko'p.", { headers: { "Retry-After": "30" } }) });
    const err = await api.get("x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect([e.status, e.code, e.message, e.requestId, e.retryAfter]).toEqual([429, "rate_limited", "So'rovlar juda ko'p.", "req-12345678", 30]);
  });

  it("JSON bo'lmagan javobda ham ApiError beradi", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502 })));
    const err = (await api.get("x").catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(502);
    expect(err.code).toBe("http_error");
  });

  it("401 global yo'naltirishni ishga tushiradi, quiet401 da esa yo'q", async () => {
    mockFetch({ "GET /api/v1/servers/": apiError(401, "unauthenticated", "Avval tizimga kiring.") });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await expect(api.get("servers/")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
    await expect(request("GET", "servers/", { quiet401: true })).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("204 javob undefined qaytaradi", async () => {
    setCookie("t");
    mockFetch({ "POST /api/v1/auth/logout": { status: 204 } });
    await expect(api.post("auth/logout")).resolves.toBeUndefined();
  });
});
