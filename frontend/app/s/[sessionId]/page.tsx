import { notFound } from "next/navigation";

import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { SessionGraphView } from "@/app/s/[sessionId]/SessionGraphView";
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

  return (
    <div className="flex h-screen">
      <SessionSidebar activeSessionId={session.id} />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">{session.title}</h1>
          <p className="text-xs text-muted-foreground">
            {session.goal}
          </p>
        </header>
        <section className="flex-1 overflow-hidden">
          <SessionGraphView
            sessionId={session.id}
            initialStatus={session.status}
            initialSynthesis={session.final_synthesis}
            initialNodes={session.nodes}
            initialEvaluations={session.evaluations}
          />
        </section>
      </main>
    </div>
  );
}
