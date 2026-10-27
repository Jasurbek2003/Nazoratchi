import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { api, ApiError, ensureCsrf } from "../api/client";
import { keys, useMe } from "../api/queries";
import type { Me } from "../api/types";
import { usePageTitle } from "../app/context";

const schema = z.object({
  login: z.string().trim().min(1, "Loginni kiriting."),
  password: z.string().min(1, "Parolni kiriting."),
});
type FormValues = z.infer<typeof schema>;

/** Login xatosini foydalanuvchiga tushunarli o'zbekcha xabarga aylantiradi (TZ 13.15: nima bo'ldi + nima qilish). */
export function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Login yoki parol noto'g'ri. Tekshirib, qayta kiriting.";
    if (error.status === 423) {
      const mins = error.retryAfter ? Math.max(1, Math.ceil(error.retryAfter / 60)) : null;
      return `Hisob vaqtincha bloklangan${mins ? `. ${mins} daqiqadan keyin qayta urinib ko'ring` : ". Keyinroq qayta urinib ko'ring"}.`;
    }
    if (error.status === 429) {
      const secs = error.retryAfter;
      return `Urinishlar juda ko'p${secs ? `. ${secs} soniyadan keyin qayta urinib ko'ring` : ". Birozdan keyin qayta urinib ko'ring"}.`;
    }
    if (error.code === "csrf_failed") return "Xavfsizlik tekshiruvi o'tmadi. Sahifani yangilab, qayta urinib ko'ring.";
    if (error.status >= 500) return "Server hozir javob bera olmayapti. Birozdan keyin qayta urinib ko'ring.";
    return error.message;
  }
  return "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.";
}

export default function LoginPage() {
  usePageTitle("Kirish");
  const me = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { login: "", password: "" } });

  if (me.data) return <Navigate to={from} replace />;

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await ensureCsrf();
      const res = await api.post<{ user: Me }>("auth/login", { login: values.login, password: values.password }, { quiet401: true });
      qc.setQueryData(keys.me, res.user);
      navigate(from, { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 400 && e.details.length > 0) {
        for (const d of e.details) {
          if (d.field === "login" || d.field === "password") setError(d.field, { message: d.message });
        }
      }
      setFormError(loginErrorMessage(e));
    }
  });

  return (
    <div className="grid min-h-dvh md:grid-cols-[minmax(320px,5fr)_7fr]">
      <aside className="relative hidden overflow-hidden bg-[var(--rail)] p-10 text-[var(--rail-text)] md:flex md:flex-col md:justify-between">
        <div className="flex items-center gap-2.5 text-lg font-semibold text-white">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="7" fill="#1c2a3d" />
            <path d="M5 17h5l3-8 5 15 3-9h6" fill="none" stroke="#5ee0a0" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Nazoratchi
        </div>
        <div>
          <p className="max-w-sm text-2xl font-semibold leading-snug text-white">Hamma serverlar va loyihalar holati bir qarashda.</p>
          <p className="mt-3 max-w-sm text-[var(--rail-muted)]">Muammo bo&apos;lsa, u tepada turadi. Bo&apos;lmasa, hech narsa sizni chalg&apos;itmaydi.</p>
        </div>
        <svg viewBox="0 0 400 60" className="w-full max-w-md opacity-70" aria-hidden>
          <path d="M0 34h96l14-24 22 46 18-30h56l16-12 18 26 12-8h148" fill="none" stroke="#5ee0a0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </aside>

      <main className="flex items-center justify-center px-5 py-10">
        <form onSubmit={onSubmit} noValidate className="w-full max-w-sm" aria-labelledby="login-title">
          <h1 id="login-title" className="text-2xl font-semibold">
            Tizimga kirish
          </h1>
          <p className="mt-1 text-muted">Hisobingiz ma&apos;lumotlarini kiriting.</p>

          {formError && (
            <div role="alert" className="mt-5 rounded-md border border-critical/60 bg-critical-bg px-3 py-2.5 text-critical-fg">
              {formError}
            </div>
          )}

          <div className="mt-5">
            <label htmlFor="login" className="mb-1 block font-medium">
              Login
            </label>
            <input
              id="login"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              className="field"
              aria-invalid={!!errors.login}
              aria-describedby={errors.login ? "login-err" : undefined}
              {...register("login")}
            />
            {errors.login && (
              <p id="login-err" className="mt-1 text-critical-fg">
                {errors.login.message}
              </p>
            )}
          </div>

          <div className="mt-4">
            <label htmlFor="password" className="mb-1 block font-medium">
              Parol
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="field"
              aria-invalid={!!errors.password}
              aria-describedby={errors.password ? "password-err" : undefined}
              {...register("password")}
            />
            {errors.password && (
              <p id="password-err" className="mt-1 text-critical-fg">
                {errors.password.message}
              </p>
            )}
          </div>

          <button type="submit" className="btn btn-primary mt-6 w-full" disabled={isSubmitting}>
            {isSubmitting ? "Tekshirilmoqda…" : "Kirish"}
          </button>
        </form>
      </main>
    </div>
  );
}
