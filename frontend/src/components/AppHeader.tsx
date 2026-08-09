import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../features/auth";

export function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function signOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="border-b border-ink/10 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
        <nav className="flex items-center gap-5">
          <Link className="font-bold tracking-wide text-ink" to="/workspaces">
            LEGAL MASTER
          </Link>
          <Link className="text-sm font-semibold text-ink/70 hover:text-ink" to="/workspaces">
            Workspaces
          </Link>
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-ink/60 sm:inline">{user?.email}</span>
          <button className="rounded-lg border border-ink/20 px-3 py-1.5 font-semibold" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
