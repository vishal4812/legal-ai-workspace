import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../features/auth/AuthContext";
import { documentApi, extractionApi, type DocumentExtraction } from "../features/documents";
import { workspaceApi } from "../features/workspaces";
import { DocumentExtractionPage } from "./DocumentExtractionPage";

vi.mock("../features/workspaces/workspaceApi", () => ({
  workspaceApi: { get: vi.fn() },
  membershipApi: {},
}));

vi.mock("../features/documents/documentApi", () => ({
  documentApi: { get: vi.fn() },
}));

vi.mock("../features/documents/extractionApi", () => ({
  extractionApi: {
    get: vi.fn(),
    getOrNull: vi.fn(),
    extract: vi.fn(),
  },
}));

const authValue: AuthContextValue = {
  user: {
    id: "user-1",
    email: "extract@example.com",
    first_name: "Extract",
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
  current_user_role: "MEMBER" as const,
};

const document = {
  id: "document-1",
  case_id: "case-1",
  original_filename: "agreement.pdf",
  mime_type: "application/pdf",
  file_size: 128,
  sha256_hash: "a".repeat(64),
  status: "UPLOADED" as const,
  is_active: true,
  created_by: "owner-1",
  created_at: "2026-08-09T00:00:00Z",
  updated_at: "2026-08-09T00:00:00Z",
};

const completed: DocumentExtraction = {
  id: "extraction-1",
  document_id: document.id,
  extractor_type: "pymupdf",
  extractor_version: "1.28.2",
  status: "COMPLETED",
  text_content: "[Page 1]\n\nThis Agreement is binding.",
  character_count: 37,
  page_count: 1,
  source_sha256_hash: document.sha256_hash,
  extracted_at: "2026-08-09T01:00:00Z",
  error_code: null,
  error_message: null,
  created_at: "2026-08-09T01:00:00Z",
  updated_at: "2026-08-09T01:00:00Z",
};

function Providers({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authValue}>
        <MemoryRouter
          initialEntries={[
            "/workspaces/workspace-1/cases/case-1/documents/document-1/extraction",
          ]}
        >
          <Routes>
            <Route
              path="/workspaces/:workspaceId/cases/:caseId/documents/:documentId/extraction"
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
  vi.mocked(documentApi.get).mockResolvedValue(document);
  vi.mocked(extractionApi.getOrNull).mockResolvedValue(null);
});

describe("Document extraction page", () => {
  test("member can trigger a document that is not extracted", async () => {
    vi.mocked(extractionApi.extract).mockResolvedValue(completed);
    render(<DocumentExtractionPage />, { wrapper: Providers });

    fireEvent.click(await screen.findByRole("button", { name: "Extract text" }));
    await waitFor(() => expect(extractionApi.extract).toHaveBeenCalledWith(
      "workspace-1",
      "case-1",
      "document-1",
    ));
    expect(await screen.findByText("This Agreement is binding.", { exact: false })).toBeInTheDocument();
  });

  test("viewer can read completed text but cannot trigger extraction", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue({
      ...workspace,
      current_user_role: "VIEWER",
    });
    vi.mocked(extractionApi.getOrNull).mockResolvedValue(completed);
    render(<DocumentExtractionPage />, { wrapper: Providers });

    expect(await screen.findByText("This Agreement is binding.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /extract/i })).not.toBeInTheDocument();
  });

  test("failed extraction shows safe error and retry control", async () => {
    vi.mocked(extractionApi.getOrNull).mockResolvedValue({
      ...completed,
      status: "FAILED",
      text_content: "",
      character_count: 0,
      extracted_at: null,
      error_code: "PDF_PARSE_ERROR",
      error_message: "The PDF could not be read for text extraction",
    });
    vi.mocked(extractionApi.extract).mockResolvedValue(completed);
    render(<DocumentExtractionPage />, { wrapper: Providers });

    expect(await screen.findByText("PDF_PARSE_ERROR")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry extraction" }));
    expect(await screen.findByText("This Agreement is binding.", { exact: false })).toBeInTheDocument();
  });

  test("completed empty extraction explains that OCR is deferred", async () => {
    vi.mocked(extractionApi.getOrNull).mockResolvedValue({
      ...completed,
      text_content: "",
      character_count: 0,
    });
    render(<DocumentExtractionPage />, { wrapper: Providers });

    expect(
      await screen.findByText("No machine-readable text was found. OCR is not implemented in Phase 5."),
    ).toBeInTheDocument();
  });

  test("processing extraction is read-only and refreshes automatically", async () => {
    vi.mocked(extractionApi.getOrNull).mockResolvedValue({
      ...completed,
      status: "PROCESSING",
      text_content: "",
      character_count: 0,
      extracted_at: null,
    });
    render(<DocumentExtractionPage />, { wrapper: Providers });

    expect(await screen.findByText("Extraction is processing. This page refreshes automatically."))
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /extract/i })).not.toBeInTheDocument();
  });

  test("network errors produce a visible error state", async () => {
    vi.mocked(extractionApi.getOrNull).mockRejectedValue(new Error("Network unavailable"));
    render(<DocumentExtractionPage />, { wrapper: Providers });

    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
    expect(screen.queryByRole("heading", { name: "Not extracted" })).not.toBeInTheDocument();
  });
});
