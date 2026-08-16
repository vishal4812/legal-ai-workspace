import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import {
  documentApi,
  extractionApi,
  indexingApi,
  searchApi,
  type Document as VaultDocument,
  type ExtractionStatus,
  type IndexingStatus,
} from "../features/documents";
import {
  canArchiveDocuments,
  canExtractDocumentText,
  canIndexDocuments,
  canUploadDocuments,
  workspaceApi,
} from "../features/workspaces";
import { caseApi } from "../features/cases";
import { apiErrorMessage } from "../utils/apiError";

export const DOCUMENT_UI_MAX_SIZE_BYTES = 50 * 1024 * 1024;
const MIME_BY_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

export function validateDocumentSelection(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLocaleLowerCase() ?? "";
  const expectedMime = MIME_BY_EXTENSION[extension];
  if (!expectedMime) return "Select a PDF or DOCX file.";
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > DOCUMENT_UI_MAX_SIZE_BYTES) return "The selected file exceeds 50 MiB.";
  if (file.type && file.type !== expectedMime) {
    return "The selected file extension and media type do not match.";
  }
  return null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

const EXTRACTION_LABELS: Record<ExtractionStatus, string> = {
  PENDING: "Processing",
  PROCESSING: "Processing",
  COMPLETED: "Extracted",
  FAILED: "Extraction failed",
};

const INDEX_LABELS: Record<IndexingStatus, string> = {
  PENDING: "Indexing",
  PROCESSING: "Indexing",
  COMPLETED: "Indexed",
  FAILED: "Index failed",
};

interface ExtractionControlsProps {
  workspaceId: string;
  caseId: string;
  document: VaultDocument;
  canExtract: boolean;
}

function ExtractionControls({
  workspaceId,
  caseId,
  document,
  canExtract,
}: ExtractionControlsProps) {
  const queryClient = useQueryClient();
  const queryKey = [
    "workspace",
    workspaceId,
    "case",
    caseId,
    "document",
    document.id,
    "extraction",
  ];
  const extraction = useQuery({
    queryKey,
    queryFn: () => extractionApi.getOrNull(workspaceId, caseId, document.id),
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" || query.state.data?.status === "PROCESSING"
        ? 2_000
        : false,
  });
  const trigger = useMutation({
    mutationFn: () => extractionApi.extract(workspaceId, caseId, document.id),
    onSuccess: (result) => queryClient.setQueryData(queryKey, result),
    onError: () => void extraction.refetch(),
  });
  const persistedStatus = extraction.data?.status;
  const visibleStatus = trigger.isPending ? "PROCESSING" : persistedStatus;
  const isInProgress = visibleStatus === "PENDING" || visibleStatus === "PROCESSING";

  return (
    <div className="mt-4 border-t border-ink/10 pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">
          Text: {visibleStatus ? EXTRACTION_LABELS[visibleStatus] : "Not extracted"}
        </span>
        {extraction.data && (
          <Link
            className="text-sm font-semibold text-brass underline"
            to={`/workspaces/${workspaceId}/cases/${caseId}/documents/${document.id}/extraction`}
          >
            View extraction
          </Link>
        )}
        {canExtract && !extraction.isLoading && persistedStatus !== "COMPLETED" && (
          <button
            className="rounded-lg border border-brass px-4 py-2 text-sm font-semibold text-brass disabled:opacity-60"
            disabled={trigger.isPending || isInProgress}
            onClick={() => trigger.mutate()}
          >
            {trigger.isPending
              ? "Extracting…"
              : persistedStatus === "FAILED"
                ? "Retry extraction"
                : "Extract text"}
          </button>
        )}
      </div>
      {extraction.isLoading && <p className="mt-2 text-sm text-ink/60">Loading extraction status…</p>}
      {extraction.error && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {apiErrorMessage(extraction.error)}
        </p>
      )}
      {trigger.error && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {apiErrorMessage(trigger.error)}
        </p>
      )}
    </div>
  );
}

function IndexingControls({
  workspaceId,
  caseId,
  document,
  canIndex,
}: {
  workspaceId: string;
  caseId: string;
  document: VaultDocument;
  canIndex: boolean;
}) {
  const queryClient = useQueryClient();
  const baseKey = ["workspace", workspaceId, "case", caseId, "document", document.id];
  const indexKey = [...baseKey, "index"];
  const extraction = useQuery({
    queryKey: [...baseKey, "extraction"],
    queryFn: () => extractionApi.getOrNull(workspaceId, caseId, document.id),
  });
  const documentIndex = useQuery({
    queryKey: indexKey,
    queryFn: () => indexingApi.getOrNull(workspaceId, caseId, document.id),
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" || query.state.data?.status === "PROCESSING"
        ? 2_000
        : false,
  });
  const trigger = useMutation({
    mutationFn: () => indexingApi.index(workspaceId, caseId, document.id),
    onSuccess: (result) => queryClient.setQueryData(indexKey, result),
    onError: () => void documentIndex.refetch(),
  });
  const persistedStatus = documentIndex.data?.status;
  const visibleStatus = trigger.isPending ? "PROCESSING" : persistedStatus;
  const inProgress = visibleStatus === "PENDING" || visibleStatus === "PROCESSING";
  const canTrigger = canIndex && extraction.data?.status === "COMPLETED";

  return (
    <div className="mt-4 border-t border-ink/10 pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">
          Search index: {visibleStatus ? INDEX_LABELS[visibleStatus] : "Not indexed"}
        </span>
        {documentIndex.data?.status === "COMPLETED" && (
          <span className="text-sm text-ink/60">
            {documentIndex.data.indexed_chunk_count} chunks · {documentIndex.data.embedding_model} · {documentIndex.data.embedding_dimension} dimensions
          </span>
        )}
        {canTrigger && persistedStatus !== "COMPLETED" && (
          <button
            className="rounded-lg border border-brass px-4 py-2 text-sm font-semibold text-brass disabled:opacity-60"
            disabled={trigger.isPending || inProgress}
            onClick={() => trigger.mutate()}
          >
            {trigger.isPending
              ? "Indexing…"
              : persistedStatus === "FAILED"
                ? "Retry indexing"
                : "Index for search"}
          </button>
        )}
      </div>
      {documentIndex.data?.status === "FAILED" && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {documentIndex.data.error_message ?? "The document could not be indexed."}
        </p>
      )}
      {(documentIndex.error || trigger.error) && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {apiErrorMessage(documentIndex.error ?? trigger.error)}
        </p>
      )}
    </div>
  );
}

function SemanticSearch({
  workspaceId,
  caseId,
  documents,
}: {
  workspaceId: string;
  caseId: string;
  documents: VaultDocument[];
}) {
  const [query, setQuery] = useState("");
  const search = useMutation({
    mutationFn: () => searchApi.search(workspaceId, query.trim(), caseId),
  });
  const names = new Map(documents.map((document) => [document.id, document.original_filename]));

  return (
    <section className="mt-8 rounded-xl border border-ink/10 bg-white p-6 shadow-sm">
      <h2 className="text-2xl font-bold">Semantic Search</h2>
      <p className="mt-2 text-sm text-ink/60">
        Ranked source text from indexed documents in this case. No answer or legal advice is generated.
      </p>
      <form
        className="mt-5 flex flex-col gap-3 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) search.mutate();
        }}
      >
        <label className="flex-1 text-sm font-medium">
          Search documents
          <input
            className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2"
            value={query}
            maxLength={2_000}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button
          className="self-end rounded-lg bg-ink px-5 py-2 font-semibold text-white disabled:opacity-60"
          disabled={!query.trim() || search.isPending}
        >
          {search.isPending ? "Searching…" : "Search"}
        </button>
      </form>
      {search.error && (
        <p className="mt-4 rounded-lg bg-red-50 p-4 text-red-700" role="alert">
          {apiErrorMessage(search.error)}
        </p>
      )}
      {search.data && (
        <div className="mt-6">
          <h3 className="text-lg font-bold">Semantic Search Results</h3>
          {search.data.results.length === 0 ? (
            <p className="mt-3 text-ink/60">No indexed text matched this query.</p>
          ) : (
            <ol className="mt-4 space-y-4">
              {search.data.results.map((result) => (
                <li className="rounded-lg border border-ink/10 p-4" key={result.chunk_id}>
                  <p className="font-semibold">{names.get(result.document_id) ?? "Document"}</p>
                  <p className="mt-1 text-xs text-ink/60">
                    {result.page_start
                      ? `Page ${result.page_start}${result.page_end && result.page_end !== result.page_start ? `–${result.page_end}` : ""}`
                      : `Chunk ${result.chunk_index + 1}`} · Similarity {result.score.toFixed(3)}
                  </p>
                  <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-sm leading-6">
                    {result.content}
                  </pre>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}

export function DocumentVaultPage() {
  const { workspaceId = "", caseId = "" } = useParams();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  const workspace = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => workspaceApi.get(workspaceId),
    enabled: Boolean(workspaceId),
  });
  const legalCase = useQuery({
    queryKey: ["workspace", workspaceId, "case", caseId],
    queryFn: () => caseApi.get(workspaceId, caseId),
    enabled: Boolean(workspaceId && caseId),
  });
  const documents = useQuery({
    queryKey: ["workspace", workspaceId, "case", caseId, "documents"],
    queryFn: () => documentApi.list(workspaceId, caseId),
    enabled: Boolean(workspaceId && caseId),
  });

  const refreshDocuments = () =>
    queryClient.invalidateQueries({
      queryKey: ["workspace", workspaceId, "case", caseId, "documents"],
    });

  const upload = useMutation({
    mutationFn: (file: File) =>
      documentApi.upload(workspaceId, caseId, file, setUploadProgress),
    onSuccess: async () => {
      setSelectedFile(null);
      setSelectionError(null);
      setUploadProgress(0);
      if (fileInput.current) fileInput.current.value = "";
      await refreshDocuments();
    },
  });
  const archive = useMutation({
    mutationFn: (documentId: string) =>
      documentApi.archive(workspaceId, caseId, documentId),
    onSuccess: refreshDocuments,
  });
  const download = useMutation({
    mutationFn: async (document: VaultDocument) => {
      const blob = await documentApi.download(workspaceId, caseId, document.id);
      saveBlob(blob, document.original_filename);
      return document.id;
    },
  });

  const role = workspace.data?.current_user_role;
  const canUpload = role ? canUploadDocuments(role) : false;
  const canArchive = role ? canArchiveDocuments(role) : false;
  const canExtract = role ? canExtractDocumentText(role) : false;
  const canIndex = role ? canIndexDocuments(role) : false;

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setSelectionError(file ? validateDocumentSelection(file) : null);
    setUploadProgress(0);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setSelectionError("Select a PDF or DOCX file.");
      return;
    }
    const validationError = validateDocumentSelection(selectedFile);
    setSelectionError(validationError);
    if (!validationError) upload.mutate(selectedFile);
  }

  const pageError = workspace.error ?? legalCase.error ?? documents.error;
  const actionError = upload.error ?? archive.error ?? download.error;

  return (
    <main className="min-h-screen">
      <AppHeader />
      <div className="mx-auto max-w-6xl px-6 py-10">
        <Link
          className="text-sm font-semibold text-brass underline"
          to={`/workspaces/${workspaceId}/cases/${caseId}`}
        >
          ← Case details
        </Link>
        <div className="mt-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-brass">Secure document vault</p>
          <h1 className="mt-2 text-4xl font-bold">{legalCase.data?.name ?? "Documents"}</h1>
          <p className="mt-2 text-ink/60">Private retained originals. PDF and DOCX, up to 50 MiB.</p>
        </div>

        {pageError && (
          <p className="mt-6 rounded-lg bg-red-50 p-4 text-red-700" role="alert">
            {apiErrorMessage(pageError)}
          </p>
        )}
        {actionError && (
          <p className="mt-6 rounded-lg bg-red-50 p-4 text-red-700" role="alert">
            {apiErrorMessage(actionError)}
          </p>
        )}

        {canUpload && (
          <form className="mt-8 rounded-xl border border-ink/10 bg-white p-6" onSubmit={submit}>
            <h2 className="text-xl font-bold">Upload document</h2>
            <label className="mt-4 block text-sm font-medium">
              PDF or DOCX
              <input
                ref={fileInput}
                className="mt-2 block w-full rounded-lg border border-ink/20 px-3 py-2"
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                disabled={upload.isPending}
                onChange={selectFile}
              />
            </label>
            {selectedFile && (
              <p className="mt-3 text-sm text-ink/70">
                Selected: <span className="font-semibold">{selectedFile.name}</span> ({formatBytes(selectedFile.size)})
              </p>
            )}
            {selectionError && <p className="mt-3 text-sm text-red-700" role="alert">{selectionError}</p>}
            {upload.isPending && (
              <div className="mt-4" aria-label={`Upload progress ${uploadProgress}%`}>
                <div className="h-2 overflow-hidden rounded-full bg-ink/10">
                  <div className="h-full bg-brass" style={{ width: `${uploadProgress}%` }} />
                </div>
                <p className="mt-2 text-sm text-ink/60">Uploading… {uploadProgress}%</p>
              </div>
            )}
            <button
              className="mt-4 rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
              disabled={!selectedFile || Boolean(selectionError) || upload.isPending}
            >
              {upload.isPending ? "Uploading…" : "Upload document"}
            </button>
          </form>
        )}

        <SemanticSearch
          workspaceId={workspaceId}
          caseId={caseId}
          documents={documents.data ?? []}
        />

        <section className="mt-8">
          <h2 className="text-2xl font-bold">Documents</h2>
          {documents.isLoading && <p className="mt-5 text-ink/60">Loading documents…</p>}
          {documents.data?.length === 0 && (
            <p className="mt-5 rounded-xl border border-dashed border-ink/20 bg-white p-8 text-ink/60">
              No documents have been uploaded to this case.
            </p>
          )}
          <div className="mt-5 space-y-4">
            {documents.data?.map((document) => (
              <article className="rounded-xl border border-ink/10 bg-white p-5 shadow-sm" key={document.id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-bold">{document.original_filename}</h3>
                    <p className="mt-1 text-sm text-ink/60">
                      {formatBytes(document.file_size)} · {document.mime_type}
                    </p>
                    <p className="mt-2 break-all font-mono text-xs text-ink/50">
                      SHA-256 {document.sha256_hash}
                    </p>
                    <p className="mt-2 text-xs text-ink/50">
                      Uploaded {new Date(document.created_at).toLocaleString()}
                    </p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${
                    document.is_active ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-800"
                  }`}>
                    {document.is_active ? document.status : "ARCHIVED"}
                  </span>
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="rounded-lg border border-ink/20 px-4 py-2 text-sm font-semibold disabled:opacity-60"
                    disabled={download.isPending}
                    onClick={() => download.mutate(document)}
                  >
                    Download
                  </button>
                  {canArchive && document.is_active && (
                    <button
                      className="rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-60"
                      disabled={archive.isPending}
                      onClick={() => archive.mutate(document.id)}
                    >
                      Archive
                    </button>
                  )}
                </div>
                <ExtractionControls
                  workspaceId={workspaceId}
                  caseId={caseId}
                  document={document}
                  canExtract={canExtract}
                />
                <IndexingControls
                  workspaceId={workspaceId}
                  caseId={caseId}
                  document={document}
                  canIndex={canIndex}
                />
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
