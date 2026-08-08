import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../features/auth";

export function RegisterPage() {
  const { register, error, clearError } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearError();
    setSubmitting(true);
    try {
      await register({
        email,
        password,
        first_name: firstName || undefined,
        last_name: lastName || undefined,
      });
      navigate("/dashboard", { replace: true });
    } catch {
      // AuthProvider exposes a safe user-facing error.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-6 py-12">
      <section className="w-full max-w-md rounded-2xl border border-ink/10 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brass">LEGAL MASTER</p>
        <h1 className="mt-3 text-3xl font-bold">Create account</h1>
        <form className="mt-8 space-y-5" onSubmit={submit}>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium">
              First name
              <input
                className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2"
                autoComplete="given-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
              />
            </label>
            <label className="block text-sm font-medium">
              Last name
              <input
                className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2"
                autoComplete="family-name"
                value={lastName}
                onChange={(event) => setLastName(event.target.value)}
              />
            </label>
          </div>
          <label className="block text-sm font-medium">
            Email
            <input
              className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input
              className="mt-2 w-full rounded-lg border border-ink/20 px-3 py-2"
              type="password"
              minLength={8}
              maxLength={128}
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <p className="text-xs text-ink/60">Use at least 8 characters.</p>
          {error && (
            <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}
          <button
            className="w-full rounded-lg bg-ink px-4 py-2.5 font-semibold text-white disabled:opacity-60"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="mt-6 text-sm text-ink/70">
          Already registered?{" "}
          <Link className="font-semibold text-brass underline" to="/login">
            Sign in
          </Link>
        </p>
      </section>
    </main>
  );
}
