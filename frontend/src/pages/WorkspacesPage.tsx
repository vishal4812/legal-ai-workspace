import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { workspaceApi } from "../features/workspaces";
import { apiErrorMessage } from "../utils/apiError";

export function WorkspacesPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: workspaceApi.list,
  });
  const createWorkspace = useMutation({
    mutationFn: workspaceApi.create,
    onSuccess: async () => {
      setName("");
      setDescription("");
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createWorkspace.mutate({ name, description: description || undefined });
  }

  return (
    <main className="min-h-screen">
      <AppHeader />
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-10 lg:grid-cols-[2fr_1fr]">
        <section>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brass">Private legal environments</p>
          <h1 className="mt-2 text-4xl font-bold">Workspaces</h1>
          {workspaces.isLoading && <p className="mt-8 text-ink/60">Loading workspaces…</p>}
          {workspaces.error && <p className="mt-8 rounded-lg bg-red-50 p-4 text-red-700" role="alert">{apiErrorMessage(workspaces.error)}</p>}
          {workspaces.data?.length === 0 && (
            <p className="mt-8 rounded-xl border border-dashed border-ink/20 bg-white p-8 text-ink/60">
              No workspaces yet. Create your first private legal environment.
            </p>
          )}
          <div className="mt-8 grid gap-4">
            {workspaces.data?.map((workspace) => (
              <Link
                className="rounded-xl border border-ink/10 bg-white p-5 shadow-sm transition hover:border-brass/50"
                key={workspace.id}
                to={`/workspaces/${workspace.id}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-xl font-bold">{workspace.name}</h2>
                  <span className="rounded-full bg-parchment px-3 py-1 text-xs font-bold">{workspace.current_user_role}</span>
                </div>
                <p className="mt-2 text-sm text-ink/65">{workspace.description ?? "No description"}</p>
                {!workspace.is_active && <p className="mt-3 text-sm font-semibold text-red-700">Archived workspace</p>}
              </Link>
            ))}
          </div>
        </section>

        <aside className="h-fit rounded-xl border border-ink/10 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-bold">Create workspace</h2>
          <form className="mt-5 space-y-4" onSubmit={submit}>
            <label className="block text-sm font-medium">
              Name
              <input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              Description
              <textarea className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            {createWorkspace.error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">{apiErrorMessage(createWorkspace.error)}</p>}
            <button className="w-full rounded-lg bg-ink px-4 py-2.5 font-semibold text-white disabled:opacity-60" disabled={createWorkspace.isPending}>
              {createWorkspace.isPending ? "Creating…" : "Create workspace"}
            </button>
          </form>
        </aside>
      </div>
    </main>
  );
}
