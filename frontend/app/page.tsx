import { api, ApiError } from "@/lib/api/client";

async function fetchHealth() {
  try {
    return { ok: true as const, data: await api.healthz() };
  } catch (error) {
    const message =
      error instanceof ApiError
        ? `${error.status} ${error.message}`
        : error instanceof Error
          ? error.message
          : "unknown error";
    return { ok: false as const, message };
  }
}

export default async function HomePage() {
  const health = await fetchHealth();

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Kodoku</h1>
      <p className="mt-2 text-neutral-600 dark:text-neutral-400">
        Decision Graph AI — tree-of-thoughts planner.
      </p>

      <section className="mt-10 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
          Backend status
        </h2>
        {health.ok ? (
          <p className="mt-1 text-sm">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 align-middle" />{" "}
            <span className="align-middle">
              {health.data.status} (v{health.data.version})
            </span>
          </p>
        ) : (
          <p className="mt-1 text-sm">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500 align-middle" />{" "}
            <span className="align-middle">unreachable — {health.message}</span>
          </p>
        )}
      </section>
    </main>
  );
}
