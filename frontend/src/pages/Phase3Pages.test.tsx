import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../features/auth/AuthContext";
import { caseApi } from "../features/cases";
import { membershipApi, workspaceApi } from "../features/workspaces";
import { CaseDetailPage } from "./CaseDetailPage";
import { CasesPage } from "./CasesPage";
import { WorkspaceDetailPage } from "./WorkspaceDetailPage";

vi.mock("../features/workspaces/workspaceApi", () => ({
  workspaceApi: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    archive: vi.fn(),
  },
  membershipApi: {
    list: vi.fn(),
    add: vi.fn(),
    changeRole: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("../features/cases/caseApi", () => ({
  caseApi: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    archive: vi.fn(),
  },
}));

const user = {
  id: "user-1",
  email: "viewer@example.com",
  first_name: "Read",
  last_name: "Only",
  is_active: true,
  is_verified: false,
  created_at: "2026-08-08T00:00:00Z",
  last_login_at: null,
};

const authValue: AuthContextValue = {
  user,
  isLoading: false,
  error: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  clearError: vi.fn(),
};

const workspace = {
  id: "workspace-1",
  name: "Read-only workspace",
  description: "Private",
  owner_id: "owner-1",
  is_active: true,
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-08T00:00:00Z",
  current_user_role: "VIEWER" as const,
};

const legalCase = {
  id: "case-1",
  workspace_id: workspace.id,
  name: "Viewed case",
  reference_number: null,
  description: "Read-only matter",
  status: "ACTIVE" as const,
  created_by: "owner-1",
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-08T00:00:00Z",
  is_active: true,
};

function Providers({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authValue}>{children}</AuthContext.Provider>
    </QueryClientProvider>
  );
}

function renderRoute(element: ReactElement, path: string, route: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path={route} element={element} /></Routes>
    </MemoryRouter>,
    { wrapper: Providers },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(workspaceApi.get).mockResolvedValue(workspace);
  vi.mocked(membershipApi.list).mockResolvedValue([]);
  vi.mocked(caseApi.list).mockResolvedValue([legalCase]);
  vi.mocked(caseApi.get).mockResolvedValue(legalCase);
});

describe("Phase 3 authorization-aware pages", () => {
  test("viewer workspace page hides mutation and membership controls", async () => {
    renderRoute(<WorkspaceDetailPage />, "/workspaces/workspace-1", "/workspaces/:workspaceId");

    expect(await screen.findByRole("heading", { name: workspace.name })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Workspace settings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add member" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View cases" })).toBeInTheDocument();
  });

  test("viewer cases page hides case creation", async () => {
    renderRoute(<CasesPage />, "/workspaces/workspace-1/cases", "/workspaces/:workspaceId/cases");

    expect(await screen.findByText(legalCase.name)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Create case" })).not.toBeInTheDocument();
  });

  test("viewer case detail is read-only", async () => {
    renderRoute(
      <CaseDetailPage />,
      "/workspaces/workspace-1/cases/case-1",
      "/workspaces/:workspaceId/cases/:caseId",
    );

    expect(await screen.findByRole("heading", { name: legalCase.name })).toBeInTheDocument();
    expect(screen.getByText(legalCase.description)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save case" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive case" })).not.toBeInTheDocument();
  });
});
