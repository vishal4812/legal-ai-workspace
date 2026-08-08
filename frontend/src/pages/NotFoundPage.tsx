import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center p-6 text-center">
      <div>
        <p className="text-sm uppercase tracking-widest text-brass">404</p>
        <h1 className="mt-2 text-3xl font-bold">Page not found</h1>
        <Link className="mt-6 inline-block underline" to="/">
          Return home
        </Link>
      </div>
    </main>
  );
}
