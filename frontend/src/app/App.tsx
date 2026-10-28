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
const IncidentsPage = lazy(() => import("../pages/IncidentsPage"));
const IncidentPage = lazy(() => import("../pages/IncidentPage"));
const BackupsPage = lazy(() => import("../pages/BackupsPage"));
const BackupPage = lazy(() => import("../pages/BackupPage"));
const DomainsPage = lazy(() => import("../pages/DomainsPage"));
const DomainPage = lazy(() => import("../pages/DomainPage"));
const MaintenancePage = lazy(() => import("../pages/MaintenancePage"));
const SettingsPage = lazy(() => import("../pages/SettingsPage"));
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
      { path: "/incidents", element: <IncidentsPage /> },
      { path: "/incidents/:id", element: <IncidentPage /> },
      { path: "/backups", element: <BackupsPage /> },
      { path: "/backups/:slug", element: <BackupPage /> },
      { path: "/domains", element: <DomainsPage /> },
      { path: "/domains/:id", element: <DomainPage /> },
      { path: "/maintenance", element: <MaintenancePage /> },
      { path: "/settings", element: <SettingsPage /> },
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
