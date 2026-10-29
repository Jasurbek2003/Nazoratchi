/**
 * API klienti: sessiya cookie (`nzr_sid`, HttpOnly) + CSRF (`csrftoken` cookie -> `X-CSRFToken`).
 * Xato formati: `{"error": {"code","message","details":[{field,code,message}],"request_id"}}` (TZ 9.1.1).
 */

export interface ErrorDetail {
  field: string;
  code: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];
  readonly requestId: string | null;
  readonly retryAfter: number | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: ErrorDetail[];
    requestId?: string | null;
    retryAfter?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? [];
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
  }
}

const API_PREFIX = "/api/v1";
const CSRF_COOKIE = "csrftoken";
const CSRF_HEADER = "X-CSRFToken";

let unauthorizedHandler: (() => void) | null = null;

/** 401 kelganda chaqiriladi (login sahifasiga yo'naltirish). `auth/login` ning o'z 401 i bundan mustasno. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

export function readCookie(name: string): string | null {
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

let csrfInflight: Promise<string> | null = null;

/** CSRF cookie yo'q bo'lsa `GET /auth/csrf` bilan oladi. */
export async function ensureCsrf(force = false): Promise<string> {
  if (!force) {
    const existing = readCookie(CSRF_COOKIE);
    if (existing) return existing;
  }
  csrfInflight ??= (async () => {
    try {
      const res = await fetch(`${API_PREFIX}/auth/csrf`, { credentials: "same-origin" });
      if (!res.ok) throw await toApiError(res);
      return readCookie(CSRF_COOKIE) ?? "";
    } finally {
      csrfInflight = null;
    }
  })();
  return csrfInflight;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const url = path.startsWith("/") ? path : `${API_PREFIX}/${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `So'rov bajarilmadi (${res.status}).`;
  let details: ErrorDetail[] = [];
  let requestId: string | null = res.headers.get("X-Request-ID");
  try {
    const body: unknown = await res.json();
    const err = (body as { error?: Record<string, unknown> } | null)?.error;
    if (err) {
      if (typeof err.code === "string") code = err.code;
      if (typeof err.message === "string") message = err.message;
      if (Array.isArray(err.details)) details = err.details as ErrorDetail[];
      if (typeof err.request_id === "string") requestId = err.request_id;
    }
  } catch {
    /* JSON bo'lmagan javob (masalan, proksi 502) */
  }
  const retry = Number(res.headers.get("Retry-After"));
  return new ApiError({
    status: res.status,
    code,
    message,
    details,
    requestId,
    retryAfter: Number.isFinite(retry) && retry > 0 ? retry : null,
  });
}

export interface RequestOptions {
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
  /** `true` bo'lsa 401 global yo'naltirishni ishga tushirmaydi (masalan, `auth/me` va login). */
  quiet401?: boolean;
}

async function send(method: string, path: string, opts: RequestOptions, csrfRetry: boolean): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const unsafe = method !== "GET" && method !== "HEAD";
  let body: string | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (unsafe) headers[CSRF_HEADER] = await ensureCsrf(false);
  const res = await fetch(buildUrl(path, opts.query), {
    method,
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
  });
  if (res.status === 403 && unsafe && csrfRetry) {
    const err = await toApiError(res.clone());
    if (err.code === "csrf_failed") {
      await ensureCsrf(true);
      return send(method, path, opts, false);
    }
  }
  return res;
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(method.toUpperCase(), path, opts, true);
  if (!res.ok) {
    const err = await toApiError(res);
    if (res.status === 401 && !opts.quiet401) unauthorizedHandler?.();
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
  post: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, "body"> = {}) =>
    request<T>("POST", path, { ...opts, body }),
  delete: <T>(path: string, opts: Omit<RequestOptions, "body"> = {}) => request<T>("DELETE", path, opts),
};
