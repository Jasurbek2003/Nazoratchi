import { useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import type { Me } from "../api/types";

/** Layout orqali beriladigan joriy foydalanuvchi. */
export function useCurrentUser(): Me {
  return useOutletContext<Me>();
}

export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · Nazoratchi`;
  }, [title]);
}
