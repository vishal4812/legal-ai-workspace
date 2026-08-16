import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { documentApi, extractionApi } from "../features/documents";
import { canExtractDocumentText, workspaceApi } from "../features/workspaces";
import { apiErrorMessage } from "../utils/apiError";

export function DocumentExtractionPage() {
  const { workspaceId = "", caseId = "", documentId = "" } = useParams();
  const queryClient = useQueryClient();
  const extractionKey = [
    "workspace",
    workspaceId,
    "case",
    caseId,
    "document",
    documentId,
    "extraction",
  ];
  const workspace = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => workspaceApi.get(workspaceId),
    enabled: Boolean(workspaceId),
  });
  const document = useQuery({
    queryKey: ["workspace", workspaceId, "case", caseId, "document", documentId],
    queryFn: () => documentApi.get(workspaceId, caseId, documentId),
    enabled: Boolean(workspaceId && caseId && documentId),
  });
  const extraction = useQuery({
    queryKey: extractionKey,
    queryFn: () => extractionApi.getOrNull(workspaceId, caseId, documentId),
    enabled: Boolean(workspaceId && caseId && documentId),
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" || query.state.data?.status === "PROCESSING"
        ? 2_000
        : false,
  });
  const trigger = useMutation({
    mutationFn: () => extractionApi.extract(workspaceId, caseId, documentId),
    onSuccess: (result) => queryClient.setQueryData(extractionKey, result),
    onError: () => void extraction.refetch(),
  });

  const role = workspace.data?.current_user_role;
  const canExtract = role ? canExtractDocumentText(role) : false;
  const result = extraction.data;
  const inProgress =
    trigger.isPending || result?.status === "PENDING" || result?.status === "PROCESSING";
  const pageError = workspace.error ?? document.error ?? extraction.error;

  return (
    <main className="min-h-screen">
      <AppHeader />
      <div className="mx-auto max-w-5xl px-6 py-10">
        <Link
          className="text-sm font-semibold text-brass underline"
          to={`/workspaces/${workspaceId}/cases/${caseId}/documents`}
        >
          ← Document vault
        </Link>
        <p className="mt-6 text-sm font-semibold uppercase tracking-wide text-brass">
          Read-only extracted text
        </p>
        <h1 className="mt-2 break-words text-4xl font-bold">
          {document.data?.original_filename ?? "Document extraction"}
        </h1>

        {pageError && (
          <p className="mt-6 rounded-lg bg-red-50 p-4 text-red-700" role="alert">
            {apiErrorMessage(pageError)}
          </p>
        )}
        {trigger.error && (
          <p className="mt-6 rounded-lg bg-red-50 p-4 text-red-700" role="alert">
            {apiErrorMessage(trigger.error)}
          </p>
        )}

        {(document.isLoading || workspace.isLoading || extraction.isLoading) && (
          <p className="mt-6 text-ink/60">Loading extraction…</p>
        )}

        {!pageError && document.data && !extraction.isLoading && !result && (
          <section className="mt-8 rounded-xl border border-dashed border-ink/20 bg-white p-8">
            <h2 className="text-xl font-bold">Not extracted</h2>
            <p className="mt-2 text-ink/60">
              This document does not yet have a machine-readable text result.
            </p>
            {canExtract && (
              <button
                className="mt-5 rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
                disabled={trigger.isPending}
                onClick={() => trigger.mutate()}
              >
                {trigger.isPending ? "Extracting…" : "Extract text"}
              </button>
            )}
          </section>
        )}

        {result && (
          <>
            <section className="mt-8 rounded-xl border border-ink/10 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold">Extraction details</h2>
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="font-semibold text-ink/60">Status</dt>
                      <dd>{trigger.isPending ? "PROCESSING" : result.status}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/60">Extractor</dt>
                      <dd>{result.extractor_type} {result.extractor_version}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/60">Characters</dt>
                      <dd>{result.character_count.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/60">Pages</dt>
                      <dd>{result.page_count ?? "Not applicable"}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/60">Extracted</dt>
                      <dd>{result.extracted_at ? new Date(result.extracted_at).toLocaleString() : "Not completed"}</dd>
                    </div>
                  </dl>
                </div>
                {canExtract && result.status === "FAILED" && (
                  <button
                    className="rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
                    disabled={inProgress}
                    onClick={() => trigger.mutate()}
                  >
                    {trigger.isPending ? "Retrying…" : "Retry extraction"}
                  </button>
                )}
              </div>
              {result.status === "FAILED" && (
                <div className="mt-5 rounded-lg bg-red-50 p-4 text-red-800">
                  <p className="font-semibold">{result.error_code ?? "EXTRACTION_FAILED"}</p>
                  <p className="mt-1">{result.error_message ?? "The document could not be extracted."}</p>
                </div>
              )}
              {inProgress && !trigger.isPending && (
                <p className="mt-5 text-ink/60">Extraction is processing. This page refreshes automatically.</p>
              )}
            </section>

            {result.status === "COMPLETED" && (
              <section className="mt-8 rounded-xl border border-ink/10 bg-white p-6 shadow-sm">
                <h2 className="text-xl font-bold">Extracted text</h2>
                {result.text_content ? (
                  <pre className="mt-5 max-h-[65vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-stone-50 p-5 font-mono text-sm leading-6">
                    {result.text_content}
                  </pre>
                ) : (
                  <p className="mt-4 rounded-lg bg-amber-50 p-4 text-amber-900">
                    No machine-readable text was found. OCR is not implemented in Phase 5.
                  </p>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}
