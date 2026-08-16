import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../features/auth/AuthContext";
import { caseApi } from "../features/cases";
import { documentApi, extractionApi, indexingApi, searchApi } from "../features/documents";
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

vi.mock("../features/documents/extractionApi", () => ({
  extractionApi: {
    get: vi.fn(),
    getOrNull: vi.fn(),
    extract: vi.fn(),
  },
}));

vi.mock("../features/documents/indexingApi", () => ({
  indexingApi: {
    get: vi.fn(),
    getOrNull: vi.fn(),
    index: vi.fn(),
  },
}));

vi.mock("../features/documents/searchApi", () => ({
  searchApi: { search: vi.fn() },
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
  vi.mocked(extractionApi.getOrNull).mockResolvedValue(null);
  vi.mocked(indexingApi.getOrNull).mockResolvedValue(null);
});

describe("Document Vault page", () => {
  test("viewer can see and download retained metadata but not upload or archive", async () => {
    render(<DocumentVaultPage />, { wrapper: Providers });

    expect(await screen.findByRole("heading", { name: legalCase.name })).toBeInTheDocument();
    expect(screen.getByText(document.original_filename)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(await screen.findByText("Text: Not extracted")).toBeInTheDocument();
    expect(await screen.findByText("Search index: Not indexed")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Semantic Search" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Extract text" })).not.toBeInTheDocument();
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
    expect(await screen.findByRole("button", { name: "Extract text" })).toBeInTheDocument();
  });

  test("shows completed extraction status and detail link", async () => {
    vi.mocked(extractionApi.getOrNull).mockResolvedValue({
      id: "extraction-1",
      document_id: document.id,
      extractor_type: "pymupdf",
      extractor_version: "1.28.2",
      status: "COMPLETED",
      text_content: "[Page 1]\n\nAgreement",
      character_count: 28,
      page_count: 1,
      parser_metadata: {
        method: "direct_text",
        engine: "pymupdf",
        direct_text_pages: [1],
        ocr_pages: [],
      },
      source_sha256_hash: document.sha256_hash,
      extracted_at: "2026-08-09T01:00:00Z",
      error_code: null,
      error_message: null,
      created_at: "2026-08-09T01:00:00Z",
      updated_at: "2026-08-09T01:00:00Z",
    });
    render(<DocumentVaultPage />, { wrapper: Providers });

    expect(await screen.findByText("Text: Extracted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View extraction" })).toHaveAttribute(
      "href",
      "/workspaces/workspace-1/cases/case-1/documents/document-1/extraction",
    );
  });

  test("authorized member can index completed extraction and sees completed metadata", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue({
      ...workspace,
      current_user_role: "MEMBER",
    });
    vi.mocked(extractionApi.getOrNull).mockResolvedValue({
      id: "extraction-1",
      document_id: document.id,
      extractor_type: "pymupdf",
      extractor_version: "1.28.2",
      status: "COMPLETED",
      text_content: "[Page 1]\n\nAgreement",
      character_count: 21,
      page_count: 1,
      parser_metadata: { method: "direct_text" },
      source_sha256_hash: document.sha256_hash,
      extracted_at: "2026-08-09T01:00:00Z",
      error_code: null,
      error_message: null,
      created_at: "2026-08-09T01:00:00Z",
      updated_at: "2026-08-09T01:00:00Z",
    });
    render(<DocumentVaultPage />, { wrapper: Providers });
    expect(await screen.findByRole("button", { name: "Index for search" })).toBeInTheDocument();

    vi.mocked(indexingApi.index).mockResolvedValue({
      id: "index-1",
      document_id: document.id,
      status: "COMPLETED",
      embedding_provider: "local",
      embedding_model: "jinaai/jina-embeddings-v2-small-en",
      embedding_dimension: 512,
      indexed_chunk_count: 3,
      source_extraction_sha256: "b".repeat(64),
      qdrant_collection: "legal_master_document_chunks",
      error_code: null,
      error_message: null,
      started_at: "2026-08-09T01:01:00Z",
      completed_at: "2026-08-09T01:02:00Z",
      created_at: "2026-08-09T01:01:00Z",
      updated_at: "2026-08-09T01:02:00Z",
    });
    fireEvent.click(screen.getByRole("button", { name: "Index for search" }));
    expect(await screen.findByText(/3 chunks.*512 dimensions/)).toBeInTheDocument();
  });

  test("viewer can search ranked source chunks but has no indexing control", async () => {
    vi.mocked(searchApi.search).mockResolvedValue({
      results: [
        {
          chunk_id: "chunk-1",
          document_id: document.id,
          case_id: legalCase.id,
          chunk_index: 0,
          content: "The termination clause requires written notice.",
          score: 0.8765,
          page_start: 2,
          page_end: 3,
          metadata: {},
        },
      ],
    });
    render(<DocumentVaultPage />, { wrapper: Providers });
    const input = await screen.findByLabelText("Search documents");
    fireEvent.change(input, { target: { value: "termination clause" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("heading", { name: "Semantic Search Results" })).toBeInTheDocument();
    expect(screen.getByText("The termination clause requires written notice.")).toBeInTheDocument();
    expect(screen.getByText(/Page 2–3/)).toHaveTextContent("Similarity 0.876");
    expect(searchApi.search).toHaveBeenCalledWith("workspace-1", "termination clause", "case-1");
    expect(screen.queryByRole("button", { name: /Index for search|Retry indexing/ })).not.toBeInTheDocument();
  });

  test("authorized member sees a safe failed state and retry control", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue({
      ...workspace,
      current_user_role: "MEMBER",
    });
    vi.mocked(extractionApi.getOrNull).mockResolvedValue({
      id: "extraction-1",
      document_id: document.id,
      extractor_type: "pymupdf",
      extractor_version: "1.28.2",
      status: "COMPLETED",
      text_content: "Agreement",
      character_count: 9,
      page_count: 1,
      parser_metadata: { method: "direct_text" },
      source_sha256_hash: document.sha256_hash,
      extracted_at: "2026-08-09T01:00:00Z",
      error_code: null,
      error_message: null,
      created_at: "2026-08-09T01:00:00Z",
      updated_at: "2026-08-09T01:00:00Z",
    });
    vi.mocked(indexingApi.getOrNull).mockResolvedValue({
      id: "index-1",
      document_id: document.id,
      status: "FAILED",
      embedding_provider: "local",
      embedding_model: "jinaai/jina-embeddings-v2-small-en",
      embedding_dimension: 512,
      indexed_chunk_count: 0,
      source_extraction_sha256: "b".repeat(64),
      qdrant_collection: "legal_master_document_chunks",
      error_code: "QDRANT_INDEXING_FAILED",
      error_message: "The document vector index could not be updated",
      started_at: "2026-08-09T01:01:00Z",
      completed_at: null,
      created_at: "2026-08-09T01:01:00Z",
      updated_at: "2026-08-09T01:02:00Z",
    });
    render(<DocumentVaultPage />, { wrapper: Providers });
    expect(await screen.findByText("Search index: Index failed")).toBeInTheDocument();
    expect(screen.getByText("The document vector index could not be updated")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry indexing" })).toBeInTheDocument();
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
