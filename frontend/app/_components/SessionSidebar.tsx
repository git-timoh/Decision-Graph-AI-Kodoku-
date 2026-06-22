"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api/client";
import { useSessionStore } from "@/state/sessionStore";
import type { SessionListItem } from "@/lib/types/api";
import { cn } from "@/lib/utils";

type Props = {
  activeSessionId?: string;
};

export function SessionSidebar({ activeSessionId }: Props) {
  const [sessions, setSessions] = useState<SessionListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tick = useSessionStore((s) => s.sidebarRefreshTick);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .listSessions()
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? `${err.status} ${err.message}`
            : err instanceof Error
              ? err.message
              : "unknown error";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-border bg-card">
      <div className="flex items-start justify-between px-4 py-5">
        <div>
          <Link href="/" className="text-lg font-semibold tracking-tight">
            Kodoku
          </Link>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Decision Graph AI
          </p>
        </div>
        <Link
          href="/settings"
          className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          Settings
        </Link>
      </div>
      <div className="px-4 pb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Sessions
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {sessions === null && !error ? (
          <p className="px-2 text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="px-2 text-sm text-destructive">Backend unreachable: {error}</p>
        ) : (sessions ?? []).length === 0 ? (
          <p className="px-2 text-sm text-muted-foreground">
            No sessions yet. Click &quot;New session&quot; to start.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {(sessions ?? []).map((row) => (
              <li key={row.id}>
                <Link
                  href={`/s/${row.id}`}
                  className={cn(
                    "block rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                    row.id === activeSessionId && "bg-accent font-medium",
                  )}
                >
                  <span className="block truncate">{row.title}</span>
                  <span className="block text-[10px] uppercase tracking-wide text-muted-foreground">
                    {row.status}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </aside>
  );
}
