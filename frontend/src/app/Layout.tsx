import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useLogout } from "../api/queries";
import type { Me } from "../api/types";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { StaleChip } from "../components/Indicators";
import { ageSeconds, formatAgo } from "../lib/format";
import { STALE_AFTER_S } from "../lib/freshness";
import { setThemePref, usePrefTheme, type ThemePref } from "../lib/theme";
import { useNow } from "../lib/useNow";

const ROLE_LABEL: Record<Me["role"], string> = { owner: "Egasi", operator: "Operator", viewer: "Kuzatuvchi" };

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
  icon: ReactNode;
}

const NAV: NavItem[] = [
  {
    to: "/",
    label: "Bosh sahifa",
    end: true,
    icon: <path d="M2.5 8.5L10 2.5l7.5 6M4.5 7.5V16h4v-4.5h3V16h4V7.5" />,
  },
  {
    to: "/servers",
    label: "Serverlar",
    icon: (
      <>
        <rect x="3" y="3.5" width="14" height="5" rx="1.2" />
        <rect x="3" y="11.5" width="14" height="5" rx="1.2" />
        <path d="M6 6h.01M6 14h.01" />
      </>
    ),
  },
  {
    to: "/projects",
    label: "Loyihalar",
    icon: <path d="M3 5.5A1.5 1.5 0 014.5 4h3l1.5 2h6.5A1.5 1.5 0 0117 7.5v7a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 013 14.5v-9z" />,
  },
  {
    to: "/incidents",
    label: "Incidentlar",
    icon: <path d="M10 2.8l7.4 13H2.6L10 2.8zM10 8v3.5M10 13.8v.1" />,
  },
  {
    to: "/backups",
    label: "Zaxiralar",
    icon: (
      <>
        <ellipse cx="10" cy="5" rx="6" ry="2.4" />
        <path d="M4 5v10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V5M4 10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4" />
      </>
    ),
  },
  {
    to: "/domains",
    label: "Domenlar",
    icon: (
      <>
        <circle cx="10" cy="10" r="7" />
        <path d="M3 10h14M10 3c2 2 3 4.4 3 7s-1 5-3 7c-2-2-3-4.4-3-7s1-5 3-7z" />
      </>
    ),
  },
  {
    to: "/maintenance",
    label: "Texnik ish",
    icon: <path d="M12.5 3.5a3.5 3.5 0 00-3.2 4.8L3.5 14.1a1.5 1.5 0 002.1 2.1l5.8-5.8a3.5 3.5 0 004.8-3.2l-2.2 2.2-1.9-.5-.5-1.9 2.2-2.2-.3-.3z" />,
  },
  {
    to: "/settings",
    label: "Sozlamalar",
    icon: (
      <>
        <circle cx="10" cy="10" r="2.6" />
        <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4" />
      </>
    ),
  },
];

/** Mobil pastki panelda to'g'ridan-to'g'ri ko'rinadigan bo'limlar; qolganlari "Yana" menyusida. */
const MOBILE_PRIMARY = ["/", "/servers", "/projects", "/incidents"];
const MOBILE_PRIMARY_ITEMS = NAV.filter((n) => MOBILE_PRIMARY.includes(n.to));
const MOBILE_MORE_ITEMS = NAV.filter((n) => !MOBILE_PRIMARY.includes(n.to));

function MobileNav() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const moreActive = MOBILE_MORE_ITEMS.some((n) => location.pathname.startsWith(n.to));
  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const cell = (active: boolean) =>
    `flex min-h-14 flex-col items-center justify-center gap-0.5 px-0.5 text-[11px] font-medium leading-tight ${active ? "text-white" : "text-[var(--rail-muted)]"}`;
  return (
    <nav aria-label="Asosiy navigatsiya (mobil)" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-[var(--rail-border)] bg-[var(--rail)] md:hidden">
      {MOBILE_PRIMARY_ITEMS.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cell(isActive)}>
          <NavIcon>{n.icon}</NavIcon>
          {n.label}
        </NavLink>
      ))}
      <button type="button" className={cell(moreActive || open)} aria-expanded={open} aria-controls="mobile-more" onClick={() => setOpen((v) => !v)}>
        <NavIcon>
          <path d="M4 10h.01M10 10h.01M16 10h.01" strokeWidth="3" />
        </NavIcon>
        Yana
      </button>
      {open && (
        <div id="mobile-more" className="absolute inset-x-2 bottom-[calc(100%+8px)] rounded-lg border border-[var(--rail-border)] bg-[var(--rail)] p-1 shadow-xl">
          {MOBILE_MORE_ITEMS.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => `flex min-h-11 items-center gap-3 rounded-md px-3 font-medium ${isActive ? "bg-[var(--rail-active)] text-white" : "text-[var(--rail-text)]"}`}
            >
              <NavIcon>{n.icon}</NavIcon>
              {n.label}
            </NavLink>
          ))}
        </div>
      )}
    </nav>
  );
}

function NavIcon({ children }: { children: ReactNode }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {children}
    </svg>
  );
}

/** "yangilandi: N soniya oldin" — kesh bo'yicha oxirgi muvaffaqiyatli yangilanish (TZ 13.2). */
function UpdatedIndicator() {
  const qc = useQueryClient();
  const now = useNow();
  const [updatedAt, setUpdatedAt] = useState(0);
  const [fetching, setFetching] = useState(false);
  useEffect(() => {
    const cache = qc.getQueryCache();
    const compute = () => {
      let max = 0;
      let busy = false;
      for (const q of cache.getAll()) {
        if (q.queryKey[0] === "me") continue;
        if (q.state.status === "success") max = Math.max(max, q.state.dataUpdatedAt);
        if (q.state.fetchStatus === "fetching") busy = true;
      }
      setUpdatedAt(max);
      setFetching(busy);
    };
    compute();
    return cache.subscribe(compute);
  }, [qc]);

  if (!updatedAt) return <span className="text-xs text-muted">yangilanmoqda…</span>;
  const age = ageSeconds(new Date(updatedAt).toISOString(), now) ?? 0;
  const stale = age > STALE_AFTER_S;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs num" aria-live="off" title="Ma'lumot har 10 soniyada avtomatik yangilanadi">
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${stale ? "bg-warning" : "bg-ok"} ${fetching ? "pulse-dot" : ""}`} />
      <span className={stale ? "text-warning-fg" : "text-muted"}>yangilandi: {formatAgo(age)}</span>
      {stale && <StaleChip />}
    </span>
  );
}

function OfflineBanner() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  if (online) return null;
  return (
    <div role="status" className="border-b border-warning/60 bg-warning-bg px-4 py-2 text-center font-medium text-warning-fg">
      Internet aloqasi yo&apos;q. Ko&apos;rsatilgan ma&apos;lumot eskirgan bo&apos;lishi mumkin.
    </div>
  );
}

const THEMES: { key: ThemePref; label: string }[] = [
  { key: "system", label: "Tizim sozlamasi" },
  { key: "light", label: "Yorug' mavzu" },
  { key: "dark", label: "Qorong'i mavzu" },
];

function UserMenu({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const theme = usePrefTheme();
  const logout = useLogout();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        ref={btnRef}
        type="button"
        className="btn gap-2"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`Foydalanuvchi menyusi: ${me.login}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden className="grid h-6 w-6 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-fg">
          {me.login.slice(0, 1).toUpperCase()}
        </span>
        <span className="max-w-28 truncate max-sm:hidden">{me.login}</span>
      </button>
      {open && (
        <div className="panel absolute right-0 z-40 mt-2 w-64 p-2 shadow-xl" role="group" aria-label="Foydalanuvchi menyusi">
          <div className="px-2 py-1.5">
            <p className="font-semibold">{me.login}</p>
            <p className="text-xs text-muted">Rol: {ROLE_LABEL[me.role]}</p>
          </div>
          <hr className="my-1 border-line" />
          <p className="px-2 pt-1 text-xs font-medium text-muted" id="theme-label">
            Mavzu
          </p>
          <div role="radiogroup" aria-labelledby="theme-label" className="mb-1">
            {THEMES.map((t) => (
              <button
                key={t.key}
                type="button"
                role="radio"
                aria-checked={theme === t.key}
                onClick={() => setThemePref(t.key)}
                className={`flex w-full items-center gap-2 rounded px-2 py-2 text-left hover:bg-surface-2 ${theme === t.key ? "font-semibold" : ""}`}
              >
                <span aria-hidden className={`h-3.5 w-3.5 rounded-full border-2 ${theme === t.key ? "border-accent bg-accent" : "border-line-strong"}`} />
                {t.label}
              </button>
            ))}
          </div>
          <hr className="my-1 border-line" />
          <button
            type="button"
            className="w-full rounded px-2 py-2 text-left font-medium hover:bg-surface-2"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            {logout.isPending ? "Chiqilmoqda…" : "Chiqish"}
          </button>
        </div>
      )}
    </div>
  );
}

function Brand() {
  return (
    <span className="flex items-center gap-2.5 font-semibold tracking-tight">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="7" fill="#1c2a3d" />
        <path d="M5 17h5l3-8 5 15 3-9h6" fill="none" stroke="#5ee0a0" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>Nazoratchi</span>
    </span>
  );
}

export function Layout({ me }: { me: Me }) {
  const location = useLocation();
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[216px_minmax(0,1fr)]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Asosiy tarkibga o&apos;tish
      </a>
      <aside className="hidden bg-[var(--rail)] text-[var(--rail-text)] md:block">
        <div className="sticky top-0 flex h-dvh flex-col px-3 py-4">
          <div className="px-2 pb-5 text-white">
            <Brand />
          </div>
          <nav aria-label="Asosiy navigatsiya" className="flex flex-col gap-0.5">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-md px-2.5 py-2 font-medium ${
                    isActive ? "bg-[var(--rail-active)] text-white" : "text-[var(--rail-text)] hover:bg-[var(--rail-active)]/60"
                  }`
                }
              >
                <NavIcon>{n.icon}</NavIcon>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <p className="mt-auto px-2 text-xs text-[var(--rail-muted)]">Infratuzilma monitoringi</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col pb-16 md:pb-0">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-surface/95 px-4 py-2 backdrop-blur md:px-6">
          <div className="md:hidden">
            <Brand />
          </div>
          <div className="hidden md:block">
            <UpdatedIndicator />
          </div>
          <div className="flex items-center gap-3">
            <div className="md:hidden">
              <UpdatedIndicator />
            </div>
            <UserMenu me={me} />
          </div>
        </header>
        <OfflineBanner />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-5 outline-none md:px-6">
          <ErrorBoundary resetKey={location.pathname}>
            <Outlet context={me} />
          </ErrorBoundary>
        </main>
      </div>

      <MobileNav />
    </div>
  );
}
