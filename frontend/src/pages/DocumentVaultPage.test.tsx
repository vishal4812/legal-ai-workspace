import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../features/auth/AuthContext";
import { caseApi } from "../features/cases";
import { documentApi } from "../features/documents";
import { workspaceApi } from "../features/workspaces";
import { DocumentVaultPage } from "./DocumentVaultPage";

vi.mock("../features/workspaces/workspaceApi", () => ({
  workspaceApi: { get: vi.fn() },
  membershipApi: {},
}));

vi.mock("../features/cases/caseApi", () => ({
  caseApi: { get: vi.fn() },
}));

vi.mock("../features/documents/documentApi", () => ({
  documentApi: {
    list: vi.fn(),
    get: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
    archive: vi.fn(),
  },
}));

const authValue: AuthContextValue = {
  user: {
    id: "user-1",
    email: "vault@example.com",
    first_name: "Vault",
    last_name: "User",
    is_active: true,
    is_verified: false,
    created_at: "2026-08-09T00:00:00Z",
    last_login_at: null,
  },
  isLoading: false,
  error: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  clearError: vi.fn(),
};

const workspace = {
  id: "workspace-1",
  name: "Legal team",
  description: null,
  owner_id: "owner-1",
  is_active: true,
  created_at: "2026-08-09T00:00:00Z",
  updated_at: "2026-08-09T00:00:00Z",
  current_user_role: "VIEWER" as const,
};

const legalCase = {
  id: "case-1",
  workspace_id: workspace.id,
  name: "Contract dispute",
  reference_number: "LM-1",
  description: null,
  status: "ACTIVE" as const,
  created_by: "owner-1",
  created_at: "2026-08-09T00:00:00Z",
  updated_at: "2026-08-09T00:00:00Z",
  is_active: true,
};

const document = {
  id: "document-1",
  case_id: legalCase.id,
  original_filename: "contract.pdf",
  mime_type: "application/pdf",
  file_size: 128,
  sha256_hash: "a".repeat(64),
  status: "UPLOADED" as const,
  is_active: true,
  created_by: "owner-1",
  created_at: "2026-08-09T00:00:00Z",
  updated_at: "2026-08-09T00:00:00Z",
};

function Providers({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={["/workspaces/workspace-1/cases/case-1/documents"]}>
          <Routes>
            <Route
              path="/workspaces/:workspaceId/cases/:caseId/documents"
              element={children}
            />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(workspaceApi.get).mockResolvedValue(workspace);
  vi.mocked(caseApi.get).mockResolvedValue(legalCase);
  vi.mocked(documentApi.list).mockResolvedValue([document]);
});

describe("Document Vault page", () => {
  test("viewer can see and download retained metadata but not upload or archive", async () => {
    render(<DocumentVaultPage />, { wrapper: Providers });

    expect(await screen.findByRole("heading", { name: legalCase.name })).toBeInTheDocument();
    expect(screen.getByText(document.original_filename)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Upload document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  });

  test("member receives upload and archive controls", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue({
      ...workspace,
      current_user_role: "MEMBER",
    });
    render(<DocumentVaultPage />, { wrapper: Providers });

    expect(await screen.findByRole("heading", { name: "Upload document" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
  });

  test("client validation rejects an unsupported extension before upload", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue({
      ...workspace,
      current_user_role: "OWNER",
    });
    render(<DocumentVaultPage />, { wrapper: Providers });
    const input = await screen.findByLabelText("PDF or DOCX");
    fireEvent.change(input, {
      target: {
        files: [new File(["binary"], "malware.exe", { type: "application/octet-stream" })],
      },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Select a PDF or DOCX file.");
    expect(screen.getByRole("button", { name: "Upload document" })).toBeDisabled();
    expect(documentApi.upload).not.toHaveBeenCalled();
  });

  test("shows backend upload progress and disables duplicate submission", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue({
      ...workspace,
      current_user_role: "OWNER",
    });
    vi.mocked(documentApi.upload).mockImplementation(
      async (_workspaceId, _caseId, _file, onProgress) => {
        onProgress?.(42);
        return await new Promise<never>(() => undefined);
      },
    );
    render(<DocumentVaultPage />, { wrapper: Providers });
    const input = await screen.findByLabelText("PDF or DOCX");
    fireEvent.change(input, {
      target: {
        files: [new File(["%PDF-1.7"], "evidence.pdf", { type: "application/pdf" })],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));

    expect(await screen.findByText("Uploading… 42%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
  });

  test("renders an empty state", async () => {
    vi.mocked(documentApi.list).mockResolvedValue([]);
    render(<DocumentVaultPage />, { wrapper: Providers });

    expect(await screen.findByText("No documents have been uploaded to this case.")).toBeInTheDocument();
  });
});
