import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { caseApi, type CaseStatus } from "../features/cases";
import { canArchiveCases, canCreateOrEditCases, workspaceApi } from "../features/workspaces";
import { apiErrorMessage } from "../utils/apiError";

export function CaseDetailPage() {
  const { workspaceId = "", caseId = "" } = useParams();
  const queryClient = useQueryClient();
  const workspace = useQuery({ queryKey: ["workspace", workspaceId], queryFn: () => workspaceApi.get(workspaceId), enabled: Boolean(workspaceId) });
  const legalCase = useQuery({ queryKey: ["workspace", workspaceId, "case", caseId], queryFn: () => caseApi.get(workspaceId, caseId), enabled: Boolean(workspaceId && caseId) });
  const [name, setName] = useState("");
  const [referenceNumber, setReferenceNumber] = useState("");
  const [description, setDescription] = useState("");
  const [caseStatus, setCaseStatus] = useState<CaseStatus>("ACTIVE");

  useEffect(() => {
    if (legalCase.data) {
      setName(legalCase.data.name);
      setReferenceNumber(legalCase.data.reference_number ?? "");
      setDescription(legalCase.data.description ?? "");
      setCaseStatus(legalCase.data.status);
    }
  }, [legalCase.data]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["workspace", workspaceId, "case", caseId] });
  const update = useMutation({
    mutationFn: () => caseApi.update(workspaceId, caseId, { name, reference_number: referenceNumber || null, description: description || null, status: caseStatus }),
    onSuccess: refresh,
  });
  const archive = useMutation({ mutationFn: () => caseApi.archive(workspaceId, caseId), onSuccess: refresh });

  if (legalCase.isLoading || workspace.isLoading) return <main className="min-h-screen"><AppHeader /><p className="mx-auto max-w-6xl px-6 py-10">Loading case…</p></main>;
  if (!legalCase.data || !workspace.data || legalCase.error || workspace.error) return <main className="min-h-screen"><AppHeader /><p className="mx-auto mt-10 max-w-6xl rounded-lg bg-red-50 p-4 text-red-700" role="alert">{apiErrorMessage(legalCase.error ?? workspace.error)}</p></main>;

  const canEdit = canCreateOrEditCases(workspace.data.current_user_role);
  const canArchive = canArchiveCases(workspace.data.current_user_role);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    update.mutate();
  }

  return (
    <main className="min-h-screen">
      <AppHeader />
      <div className="mx-auto max-w-4xl px-6 py-10">
        <Link className="text-sm font-semibold text-brass underline" to={`/workspaces/${workspaceId}/cases`}>← All cases</Link>
        <div className="mt-5 flex items-start justify-between gap-4">
          <div><h1 className="text-4xl font-bold">{legalCase.data.name}</h1><p className="mt-2 text-ink/60">{legalCase.data.reference_number ?? "No reference number"}</p></div>
          <span className="rounded-full bg-white px-3 py-1 text-xs font-bold">{legalCase.data.status}</span>
        </div>
        {!legalCase.data.is_active && <p className="mt-5 rounded-lg bg-red-50 p-4 font-semibold text-red-700">This case is archived and retained for legal history.</p>}
        {(update.error || archive.error) && <p className="mt-5 rounded-lg bg-red-50 p-4 text-red-700" role="alert">{apiErrorMessage(update.error ?? archive.error)}</p>}

        {canEdit ? (
          <form className="mt-8 space-y-5 rounded-xl border border-ink/10 bg-white p-6" onSubmit={submit}>
            <label className="block text-sm font-medium">Name<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" required value={name} onChange={(event) => setName(event.target.value)} /></label>
            <div className="grid gap-5 md:grid-cols-2">
              <label className="text-sm font-medium">Reference number<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" value={referenceNumber} onChange={(event) => setReferenceNumber(event.target.value)} /></label>
              <label className="text-sm font-medium">Status<select className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" value={caseStatus} onChange={(event) => setCaseStatus(event.target.value as CaseStatus)}><option>ACTIVE</option><option>ARCHIVED</option><option>CLOSED</option></select></label>
            </div>
            <label className="block text-sm font-medium">Description<textarea className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" rows={6} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
            <div className="flex flex-wrap gap-3">
              <button className="rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={update.isPending}>Save case</button>
              {canArchive && legalCase.data.is_active && <button className="rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700" type="button" onClick={() => archive.mutate()}>Archive case</button>}
            </div>
          </form>
        ) : (
          <section className="mt-8 rounded-xl border border-ink/10 bg-white p-6"><h2 className="font-bold">Description</h2><p className="mt-3 whitespace-pre-wrap text-ink/70">{legalCase.data.description ?? "No description"}</p></section>
        )}
      </div>
    </main>
  );
}
