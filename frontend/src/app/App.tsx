import { lazy, Suspense, useMemo } from "react";
import { createBrowserRouter, RouterProvider, Navigate, type RouteObject } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { SkeletonRows } from "../components/Feedback";
import { RequireAuth, useUnauthorizedRedirect } from "./auth";
import { Layout } from "./Layout";

const LoginPage = lazy(() => import("../pages/LoginPage"));
const DashboardPage = lazy(() => import("../pages/DashboardPage"));
const ServersPage = lazy(() => import("../pages/ServersPage"));
const ServerPage = lazy(() => import("../pages/ServerPage"));
const ProjectsPage = lazy(() => import("../pages/ProjectsPage"));
const ProjectPage = lazy(() => import("../pages/ProjectPage"));
const NotFoundPage = lazy(() => import("../pages/NotFoundPage"));

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        refetchOnWindowFocus: true,
        retry: (count, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return count < 2;
        },
      },
    },
  });
}

function Fallback() {
  return (
    <div className="p-4">
      <SkeletonRows rows={3} />
    </div>
  );
}

function Shell() {
  useUnauthorizedRedirect();
  return <RequireAuth>{(me) => <Layout me={me} />}</RequireAuth>;
}

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <Shell />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/servers", element: <ServersPage /> },
      { path: "/servers/:id", element: <ServerPage /> },
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/projects/:id", element: <ProjectPage /> },
      { path: "/home", element: <Navigate to="/" replace /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function App({ client }: { client: QueryClient }) {
  const router = useMemo(() => createBrowserRouter(routes), []);
  return (
    <ErrorBoundary>
      <QueryClientProvider client={client}>
        <Suspense fallback={<Fallback />}>
          <RouterProvider router={router} />
        </Suspense>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
