"use client";

import { useMemo, useState } from "react";
import { Check, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { Checkpoint, CheckpointCandidate } from "@/lib/ws/types";

type Decision = "keep" | "prune";

type RowEdit = {
  title: string;
  content: string;
};

function buildInitialDecisions(payload: Checkpoint["payload"]): Record<string, Decision> {
  const decisions: Record<string, Decision> = {};
  for (const candidate of payload.candidates) {
    decisions[candidate.id] = payload.proposed_keep.includes(candidate.id)
      ? "keep"
      : "prune";
  }
  return decisions;
}

function buildInitialEdits(payload: Checkpoint["payload"]): Record<string, RowEdit> {
  const edits: Record<string, RowEdit> = {};
  for (const candidate of payload.candidates) {
    edits[candidate.id] = { title: candidate.title, content: candidate.content };
  }
  return edits;
}

function dimensionKeys(candidates: CheckpointCandidate[]): string[] {
  const keys = new Set<string>();
  for (const candidate of candidates) {
    for (const key of Object.keys(candidate.dimensions ?? {})) {
      keys.add(key);
    }
  }
  return Array.from(keys).sort();
}

type Props = {
  sessionId: string;
  checkpoint: Checkpoint;
};

export function CheckpointPanel({ sessionId, checkpoint }: Props) {
  const { checkpoint_id, payload } = checkpoint;
  const { candidates } = payload;

  const [decisions, setDecisions] = useState<Record<string, Decision>>(() =>
    buildInitialDecisions(payload),
  );
  const [edits, setEdits] = useState<Record<string, RowEdit>>(() =>
    buildInitialEdits(payload),
  );
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"approve" | "proposal" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dimKeys = useMemo(() => dimensionKeys(candidates), [candidates]);

  function setDecision(id: string, decision: Decision) {
    setDecisions((prev) => ({ ...prev, [id]: decision }));
  }

  function setEdit(id: string, patch: Partial<RowEdit>) {
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  function isRowEdited(candidate: CheckpointCandidate): boolean {
    const edit = edits[candidate.id];
    if (!edit) return false;
    return edit.title !== candidate.title || edit.content !== candidate.content;
  }

  async function submit(mode: "approve" | "proposal") {
    setSubmitting(mode);
    setError(null);
    try {
      if (mode === "proposal") {
        await api.resumeSession(sessionId, {
          checkpoint_id,
          keep: payload.proposed_keep,
          prune: payload.proposed_prune,
          edits: {},
        });
        return;
      }

      const keep: string[] = [];
      const prune: string[] = [];
      const changedEdits: Record<string, { title?: string | null; content?: string | null }> =
        {};

      for (const candidate of candidates) {
        const decision = decisions[candidate.id] ?? "prune";
        if (decision === "keep") keep.push(candidate.id);
        else prune.push(candidate.id);

        if (isRowEdited(candidate)) {
          const edit = edits[candidate.id];
          changedEdits[candidate.id] = { title: edit.title, content: edit.content };
        }
      }

      await api.resumeSession(sessionId, {
        checkpoint_id,
        keep,
        prune,
        edits: changedEdits,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume session.");
      setSubmitting(null);
      return;
    }
    setSubmitting(null);
  }

  return (
    <div className="absolute inset-0 z-30 flex justify-end">
      <div
        className="absolute inset-0 bg-black/40 animate-in fade-in-0"
        aria-hidden="true"
      />
      <div
        className={cn(
          "relative flex h-full w-full max-w-3xl flex-col border-l border-border bg-card shadow-2xl",
          "animate-in slide-in-from-right duration-200",
        )}
        role="dialog"
        aria-label="Checkpoint review"
      >
        <div className="flex items-start justify-between border-b border-border px-6 py-4">
          <div>
            <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-600">
              awaiting_human
            </span>
            <h2 className="mt-2 text-sm font-semibold">Checkpoint reached</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Review the {candidates.length} candidate
              {candidates.length === 1 ? "" : "s"} below, adjust keep / prune as
              needed, then continue the run.
            </p>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-4">
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="w-[110px] px-3 py-2 font-medium">Decision</th>
                  <th className="px-3 py-2 font-medium">Candidate</th>
                  <th className="w-[64px] px-3 py-2 text-right font-medium">Score</th>
                  {dimKeys.map((key) => (
                    <th key={key} className="w-[72px] px-3 py-2 text-right font-medium">
                      {key}
                    </th>
                  ))}
                  <th className="px-3 py-2 font-medium">Critique</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate) => {
                  const decision = decisions[candidate.id] ?? "prune";
                  const edit = edits[candidate.id];
                  const edited = isRowEdited(candidate);
                  const isEditing = editingId === candidate.id;

                  return (
                    <tr
                      key={candidate.id}
                      className={cn(
                        "border-b border-border align-top last:border-b-0",
                        edited && "bg-violet-500/5",
                      )}
                    >
                      <td className="px-3 py-3">
                        <div className="inline-flex rounded-md border border-input p-0.5 text-xs font-medium">
                          <button
                            type="button"
                            onClick={() => setDecision(candidate.id, "keep")}
                            className={cn(
                              "rounded-[5px] px-2 py-1 transition-colors",
                              decision === "keep"
                                ? "bg-emerald-500/15 text-emerald-600"
                                : "text-muted-foreground hover:bg-accent",
                            )}
                          >
                            Keep
                          </button>
                          <button
                            type="button"
                            onClick={() => setDecision(candidate.id, "prune")}
                            className={cn(
                              "rounded-[5px] px-2 py-1 transition-colors",
                              decision === "prune"
                                ? "bg-red-500/15 text-red-600"
                                : "text-muted-foreground hover:bg-accent",
                            )}
                          >
                            Prune
                          </button>
                        </div>
                      </td>
                      <td className="min-w-[220px] max-w-[320px] px-3 py-3">
                        {isEditing ? (
                          <div className="flex flex-col gap-1.5">
                            <Input
                              value={edit.title}
                              onChange={(e) => setEdit(candidate.id, { title: e.target.value })}
                              className="h-8 text-sm font-medium"
                            />
                            <Textarea
                              value={edit.content}
                              onChange={(e) =>
                                setEdit(candidate.id, { content: e.target.value })
                              }
                              className="min-h-[64px] text-xs"
                            />
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 self-start px-2 text-xs"
                              onClick={() => setEditingId(null)}
                            >
                              <Check className="mr-1 h-3 w-3" />
                              Done
                            </Button>
                          </div>
                        ) : (
                          <div className="group flex items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-medium leading-snug">
                                {edit.title}
                                {edited && (
                                  <span className="ml-1.5 rounded bg-violet-500/15 px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-600">
                                    edited
                                  </span>
                                )}
                              </p>
                              <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                                {edit.content}
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => setEditingId(candidate.id)}
                              className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100"
                              aria-label="Edit candidate"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right text-sm font-semibold tabular-nums">
                        {candidate.score.toFixed(1)}
                      </td>
                      {dimKeys.map((key) => (
                        <td
                          key={key}
                          className="px-3 py-3 text-right text-xs tabular-nums text-muted-foreground"
                        >
                          {candidate.dimensions?.[key] !== undefined
                            ? candidate.dimensions[key].toFixed(1)
                            : "—"}
                        </td>
                      ))}
                      <td className="min-w-[200px] max-w-[280px] px-3 py-3 text-xs text-muted-foreground">
                        {candidate.critique}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {error && (
          <div className="border-t border-border bg-red-500/10 px-6 py-2 text-xs text-red-600">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          <Button
            variant="outline"
            size="sm"
            disabled={submitting !== null}
            onClick={() => submit("proposal")}
          >
            {submitting === "proposal" ? "Resuming…" : "Use engine proposal"}
          </Button>
          <Button size="sm" disabled={submitting !== null} onClick={() => submit("approve")}>
            {submitting === "approve" ? (
              "Resuming…"
            ) : (
              <>
                <Check className="mr-1.5 h-3.5 w-3.5" />
                Approve & continue
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
