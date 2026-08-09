import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import {
  canChangeMemberRoles,
  canManageMembers,
  canUpdateWorkspace,
  membershipApi,
  workspaceApi,
  type WorkspaceRole,
} from "../features/workspaces";
import { apiErrorMessage } from "../utils/apiError";

const assignableRoles: Exclude<WorkspaceRole, "OWNER">[] = ["ADMIN", "MEMBER", "VIEWER"];

export function WorkspaceDetailPage() {
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const workspace = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => workspaceApi.get(workspaceId),
    enabled: Boolean(workspaceId),
  });
  const members = useQuery({
    queryKey: ["workspace", workspaceId, "members"],
    queryFn: () => membershipApi.list(workspaceId),
    enabled: Boolean(workspaceId),
  });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Exclude<WorkspaceRole, "OWNER">>("MEMBER");

  useEffect(() => {
    if (workspace.data) {
      setName(workspace.data.name);
      setDescription(workspace.data.description ?? "");
    }
  }, [workspace.data]);

  const refreshWorkspace = () =>
    queryClient.invalidateQueries({ queryKey: ["workspace", workspaceId] });
  const refreshMembers = () =>
    queryClient.invalidateQueries({ queryKey: ["workspace", workspaceId, "members"] });

  const update = useMutation({
    mutationFn: () => workspaceApi.update(workspaceId, { name, description: description || null }),
    onSuccess: refreshWorkspace,
  });
  const archive = useMutation({
    mutationFn: () => workspaceApi.archive(workspaceId),
    onSuccess: refreshWorkspace,
  });
  const add = useMutation({
    mutationFn: () => membershipApi.add(workspaceId, { email, role }),
    onSuccess: async () => {
      setEmail("");
      await refreshMembers();
    },
  });
  const changeRole = useMutation({
    mutationFn: ({ userId, nextRole }: { userId: string; nextRole: Exclude<WorkspaceRole, "OWNER"> }) =>
      membershipApi.changeRole(workspaceId, userId, { role: nextRole }),
    onSuccess: refreshMembers,
  });
  const remove = useMutation({
    mutationFn: (userId: string) => membershipApi.remove(workspaceId, userId),
    onSuccess: refreshMembers,
  });

  if (workspace.isLoading) return <main className="min-h-screen"><AppHeader /><p className="mx-auto max-w-6xl px-6 py-10">Loading workspace…</p></main>;
  if (workspace.error || !workspace.data) return <main className="min-h-screen"><AppHeader /><p className="mx-auto mt-10 max-w-6xl rounded-lg bg-red-50 p-4 text-red-700" role="alert">{apiErrorMessage(workspace.error)}</p></main>;

  const current = workspace.data;
  const mayManage = canManageMembers(current.current_user_role);
  const mutationError = update.error ?? archive.error ?? add.error ?? changeRole.error ?? remove.error;

  function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <main className="min-h-screen">
      <AppHeader />
      <div className="mx-auto max-w-6xl px-6 py-10">
        <Link className="text-sm font-semibold text-brass underline" to="/workspaces">← All workspaces</Link>
        <div className="mt-5 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-4xl font-bold">{current.name}</h1>
              <span className="rounded-full bg-white px-3 py-1 text-xs font-bold">{current.current_user_role}</span>
            </div>
            <p className="mt-3 text-ink/65">{current.description ?? "No description"}</p>
            {!current.is_active && <p className="mt-3 font-semibold text-red-700">This workspace is archived.</p>}
          </div>
          <Link className="rounded-lg bg-ink px-4 py-2 font-semibold text-white" to={`/workspaces/${workspaceId}/cases`}>View cases</Link>
        </div>

        {mutationError && <p className="mt-6 rounded-lg bg-red-50 p-4 text-red-700" role="alert">{apiErrorMessage(mutationError)}</p>}

        {canUpdateWorkspace(current.current_user_role) && (
          <section className="mt-10 rounded-xl border border-ink/10 bg-white p-6">
            <h2 className="text-2xl font-bold">Workspace settings</h2>
            <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={(event) => { event.preventDefault(); update.mutate(); }}>
              <label className="text-sm font-medium">Name<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" required value={name} onChange={(event) => setName(event.target.value)} /></label>
              <label className="text-sm font-medium">Description<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
              <button className="w-fit rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={update.isPending}>Save changes</button>
              {current.current_user_role === "OWNER" && current.is_active && (
                <button className="w-fit rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700" type="button" onClick={() => archive.mutate()}>Archive workspace</button>
              )}
            </form>
          </section>
        )}

        <section className="mt-8 rounded-xl border border-ink/10 bg-white p-6">
          <h2 className="text-2xl font-bold">Members</h2>
          {mayManage && (
            <form className="mt-5 flex flex-wrap items-end gap-3 rounded-lg bg-parchment p-4" onSubmit={addMember}>
              <label className="min-w-64 flex-1 text-sm font-medium">Existing user email<input className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
              <label className="text-sm font-medium">Role<select className="mt-2 block rounded-lg border border-ink/20 px-3 py-2" value={role} onChange={(event) => setRole(event.target.value as Exclude<WorkspaceRole, "OWNER">)}>{assignableRoles.map((item) => <option key={item}>{item}</option>)}</select></label>
              <button className="rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={add.isPending}>Add member</button>
            </form>
          )}
          {members.isLoading && <p className="mt-5 text-ink/60">Loading members…</p>}
          {members.error && <p className="mt-5 text-red-700" role="alert">{apiErrorMessage(members.error)}</p>}
          <div className="mt-5 divide-y divide-ink/10">
            {members.data?.map((member) => {
              const canRemove = mayManage && member.role !== "OWNER" && !(current.current_user_role === "ADMIN" && member.role === "ADMIN");
              return (
                <div className="flex flex-wrap items-center justify-between gap-3 py-4" key={member.id}>
                  <div><p className="font-semibold">{[member.first_name, member.last_name].filter(Boolean).join(" ") || member.email}</p><p className="text-sm text-ink/60">{member.email}</p></div>
                  <div className="flex items-center gap-2">
                    {canChangeMemberRoles(current.current_user_role) && member.role !== "OWNER" ? (
                      <select aria-label={`Role for ${member.email}`} className="rounded-lg border border-ink/20 px-3 py-2 text-sm" value={member.role} onChange={(event) => changeRole.mutate({ userId: member.user_id, nextRole: event.target.value as Exclude<WorkspaceRole, "OWNER"> })}>{assignableRoles.map((item) => <option key={item}>{item}</option>)}</select>
                    ) : <span className="rounded-full bg-parchment px-3 py-1 text-xs font-bold">{member.role}</span>}
                    {canRemove && <button className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-semibold text-red-700" onClick={() => remove.mutate(member.user_id)}>Remove</button>}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
