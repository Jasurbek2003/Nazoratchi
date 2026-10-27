import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { setUnauthorizedHandler } from "../api/client";
import { keys, useMe } from "../api/queries";
import type { Me } from "../api/types";
import { ErrorState, SkeletonRows } from "../components/Feedback";

/** Har qanday API 401 -> sessiya tugagan: `me` bo'shatiladi va RequireAuth `/login` ga yo'naltiradi. */
export function useUnauthorizedRedirect(): void {
  const qc = useQueryClient();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      qc.setQueryData(keys.me, null);
    });
    return () => setUnauthorizedHandler(null);
  }, [qc]);
}

export function RequireAuth({ children }: { children: (me: Me) => ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <SkeletonRows rows={3} />
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <ErrorState error={me.error} onRetry={() => void me.refetch()} title="Sessiyani tekshirib bo'lmadi" />
      </div>
    );
  }
  if (!me.data) {
    const from = location.pathname + location.search;
    return <Navigate to="/login" replace state={{ from }} />;
  }
  return <>{children(me.data)}</>;
}
