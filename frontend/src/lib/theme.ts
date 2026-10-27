/** Mavzu: tizim (`prefers-color-scheme`) + qo'lda almashtirish (`<html data-theme>`). */
import { useSyncExternalStore } from "react";

export type ThemePref = "system" | "light" | "dark";
const KEY = "nzr_theme";
const listeners = new Set<() => void>();

export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* localStorage mavjud emas */
  }
  return "system";
}

export function applyTheme(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
}

export function setThemePref(pref: ThemePref): void {
  try {
    if (pref === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    /* e'tiborsiz */
  }
  applyTheme(pref);
  listeners.forEach((l) => l());
}

export function resolvedTheme(): "light" | "dark" {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  mq?.addEventListener("change", cb);
  return () => {
    listeners.delete(cb);
    mq?.removeEventListener("change", cb);
  };
}

/** Hozirgi (aniqlangan) mavzu — grafiklarni qayta qurish uchun. */
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, resolvedTheme, () => "light");
}

export function usePrefTheme(): ThemePref {
  return useSyncExternalStore(subscribe, getThemePref, () => "system");
}
