import { notFound } from "next/navigation";

import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { ApiError, api } from "@/lib/api/client";
import type { SessionDetailResponse } from "@/lib/types/api";

async function loadSession(id: string): Promise<SessionDetailResponse | null> {
  try {
    return await api.getSession(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

type Props = { params: { sessionId: string } };

export default async function SessionPage({ params }: Props) {
  const session = await loadSession(params.sessionId);
  if (!session) notFound();

  const root = session.nodes.find((n) => n.kind === "root");

  return (
    <div className="flex h-screen">
      <SessionSidebar activeSessionId={session.id} />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">{session.title}</h1>
          <p className="text-xs text-muted-foreground">
            Status: {session.status} · Created{" "}
            {new Date(session.created_at).toLocaleString()}
          </p>
        </header>
        <section className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-2xl space-y-6">
            <article className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Goal
              </h2>
              <p className="mt-2 whitespace-pre-wrap text-sm">{session.goal}</p>
            </article>

            {root && (
              <article className="rounded-lg border border-border bg-card p-4">
                <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Root node
                </h2>
                <p className="mt-1 text-sm font-medium">{root.title}</p>
                <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
                  {root.content}
                </p>
              </article>
            )}

            <p className="text-xs text-muted-foreground">
              Graph rendering lands in M3. Engine + Run controls land in M4.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
