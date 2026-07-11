"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";

/** Banner shown on first run when no model key is configured. BYOK means a fresh
 * install would otherwise fail only at "Run"; this points the user to Settings
 * up front. Stays hidden if a provider key or an Ollama base URL is set. */
export function FirstRunNotice() {
  const [needsKey, setNeedsKey] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .getSettings()
      .then((s) => {
        const anyKey = Object.values(s.providers).some((p) => p.set);
        const hasOllama = Boolean(s.ollama_base_url);
        if (active) setNeedsKey(!anyKey && !hasOllama);
      })
      .catch(() => {
        /* settings unreachable — stay quiet rather than raise a false alarm */
      });
    return () => {
      active = false;
    };
  }, []);

  if (!needsKey) return null;

  return (
    <div className="mx-6 mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
      <span className="font-medium">No model key set.</span> Kodoku needs an API key to run.{" "}
      <Link href="/settings" className="underline underline-offset-2">
        Add one in Settings
      </Link>{" "}
      to get started.
    </div>
  );
}
