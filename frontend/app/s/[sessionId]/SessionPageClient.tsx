"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { SessionGraphView } from "@/app/s/[sessionId]/SessionGraphView";
import { ApiError, api } from "@/lib/api/client";
import type { SessionDetailResponse } from "@/lib/types/api";

type Load =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "ready"; session: SessionDetailResponse };

export function SessionPageClient() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    let active = true;
    api
      .getSession(sessionId)
      .then((session) => active && setLoad({ state: "ready", session }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          if (active) setLoad({ state: "missing" });
          return;
        }
        throw err;
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  if (load.state === "loading") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Loading session…
      </div>
    );
  }
  if (load.state === "missing") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Session not found.
      </div>
    );
  }

  const { session } = load;
  return (
    <div className="flex h-screen">
      <SessionSidebar activeSessionId={session.id} />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">{session.title}</h1>
          <p className="text-xs text-muted-foreground">{session.goal}</p>
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
