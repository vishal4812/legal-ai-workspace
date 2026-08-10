import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { documentApi, type Document as VaultDocument } from "../features/documents";
import {
  canArchiveDocuments,
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
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
