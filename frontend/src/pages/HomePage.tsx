import { useHealth } from "../services/health";

export function HomePage() {
  const health = useHealth();

  return (
    <main className="min-h-screen px-6 py-16 sm:px-12">
      <section className="mx-auto max-w-4xl rounded-2xl border border-ink/10 bg-white/80 p-8 shadow-sm sm:p-12">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brass">Private legal workspace</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight text-ink sm:text-6xl">LEGAL MASTER</h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-ink/70">
          The Phase 1 foundation is ready. Secure document workflows and legal AI capabilities will be added incrementally.
        </p>
        <div className="mt-10 flex items-center gap-3 text-sm text-ink/70" aria-live="polite">
          <span
            className={`h-2.5 w-2.5 rounded-full ${health.isSuccess ? "bg-emerald-500" : health.isError ? "bg-red-500" : "bg-amber-500"}`}
          />
          {health.isSuccess ? "API connected" : health.isError ? "API unavailable" : "Checking API"}
        </div>
      </section>
    </main>
  );
}
