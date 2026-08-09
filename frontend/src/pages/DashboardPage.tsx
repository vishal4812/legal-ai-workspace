import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../features/auth";

export function DashboardPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function signOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <main className="min-h-screen px-6 py-12 sm:px-12">
      <section className="mx-auto max-w-5xl rounded-2xl border border-ink/10 bg-white p-8 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brass">Private legal workspace</p>
            <h1 className="mt-2 text-4xl font-bold">Welcome to LEGAL MASTER</h1>
            <p className="mt-3 text-ink/65">{user?.email}</p>
          </div>
          <button className="rounded-lg border border-ink/20 px-4 py-2 font-semibold" onClick={signOut}>
            Sign out
          </button>
        </div>
        <Link className="mt-12 block rounded-xl bg-ink p-5 font-semibold text-white" to="/workspaces">
          Open your legal workspaces →
        </Link>
      </section>
    </main>
  );
}
