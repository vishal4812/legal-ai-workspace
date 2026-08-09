import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { caseApi } from "../features/cases";
import { canCreateOrEditCases, workspaceApi } from "../features/workspaces";
import { apiErrorMessage } from "../utils/apiError";

export function CasesPage() {
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const workspace = useQuery({ queryKey: ["workspace", workspaceId], queryFn: () => workspaceApi.get(workspaceId), enabled: Boolean(workspaceId) });
  const cases = useQuery({ queryKey: ["workspace", workspaceId, "cases"], queryFn: () => caseApi.list(workspaceId), enabled: Boolean(workspaceId) });
  const [name, setName] = useState("");
  const [referenceNumber, setReferenceNumber] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation({
    mutationFn: () => caseApi.create(workspaceId, { name, reference_number: referenceNumber || undefined, description: description || undefined }),
    onSuccess: async () => {
      setName(""); setReferenceNumber(""); setDescription("");
      await queryClient.invalidateQueries({ queryKey: ["workspace", workspaceId, "cases"] });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }

  const canCreate = workspace.data ? canCreateOrEditCases(workspace.data.current_user_role) : false;

  return (
    <main className="min-h-screen">
      <AppHeader />
      <div className="mx-auto max-w-6xl px-6 py-10">
        <Link className="text-sm font-semibold text-brass underline" to={`/workspaces/${workspaceId}`}>← Workspace</Link>
        <h1 className="mt-5 text-4xl font-bold">Cases</h1>
        <p className="mt-2 text-ink/60">{workspace.data?.name ?? "Loading workspace…"}</p>
        {(workspace.error || cases.error) && <p className="mt-6 rounded-lg bg-red-50 p-4 text-red-700" role="alert">{apiErrorMessage(workspace.error ?? cases.error)}</p>}

        {canCreate && (
          <form className="mt-8 grid gap-4 rounded-xl border border-ink/10 bg-white p-6 md:grid-cols-3" onSubmit={submit}>
            <h2 className="text-xl font-bold md:col-span-3">Create case</h2>
            <label className="text-sm font-medium">Name<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" required value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label className="text-sm font-medium">Reference number<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" value={referenceNumber} onChange={(event) => setReferenceNumber(event.target.value)} /></label>
            <label className="text-sm font-medium">Description<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
            {create.error && <p className="text-sm text-red-700 md:col-span-3" role="alert">{apiErrorMessage(create.error)}</p>}
            <button className="w-fit rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={create.isPending}>Create case</button>
          </form>
        )}

        {cases.isLoading && <p className="mt-8 text-ink/60">Loading cases…</p>}
        {cases.data?.length === 0 && <p className="mt-8 rounded-xl border border-dashed border-ink/20 bg-white p-8 text-ink/60">No cases in this workspace.</p>}
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {cases.data?.map((legalCase) => (
            <Link className="rounded-xl border border-ink/10 bg-white p-5 shadow-sm" key={legalCase.id} to={`/workspaces/${workspaceId}/cases/${legalCase.id}`}>
              <div className="flex justify-between gap-3"><h2 className="text-xl font-bold">{legalCase.name}</h2><span className="text-xs font-bold">{legalCase.status}</span></div>
              <p className="mt-2 text-sm text-ink/60">{legalCase.reference_number ?? "No reference number"}</p>
              {!legalCase.is_active && <p className="mt-3 text-sm font-semibold text-red-700">Archived</p>}
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
