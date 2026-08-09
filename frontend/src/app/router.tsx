import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";

import { ProtectedRoute } from "../features/auth";
import { CaseDetailPage } from "../pages/CaseDetailPage";
import { CasesPage } from "../pages/CasesPage";
import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { RegisterPage } from "../pages/RegisterPage";
import { WorkspaceDetailPage } from "../pages/WorkspaceDetailPage";
import { WorkspacesPage } from "../pages/WorkspacesPage";

export const appRoutes: RouteObject[] = [
  { path: "/", element: <Navigate to="/dashboard" replace /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/dashboard", element: <DashboardPage /> },
      { path: "/workspaces", element: <WorkspacesPage /> },
      { path: "/workspaces/:workspaceId", element: <WorkspaceDetailPage /> },
      { path: "/workspaces/:workspaceId/cases", element: <CasesPage /> },
      { path: "/workspaces/:workspaceId/cases/:caseId", element: <CaseDetailPage /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];

export const router = createBrowserRouter(appRoutes);
