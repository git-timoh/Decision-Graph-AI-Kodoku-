"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, describeError } from "@/lib/api/client";
import { MODEL_PRESETS } from "@/lib/models";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/state/sessionStore";

const BRANCH_SLOTS = 3;

/** Sentinel for "use the Settings expand model" (Radix Select forbids ""). */
const SETTINGS_DEFAULT = "__settings_default__";

const DEPTH_OPTIONS = [
  { value: 2, label: "Quick", description: "Shallow pass — fastest and cheapest." },
  { value: 3, label: "Standard", description: "Default balance of breadth and cost." },
  {
    value: 4,
    label: "Deep",
    description: "Explores further — roughly 3× the cost of Standard.",
  },
] as const;

type HitlMode = "autopilot" | "every_branch";

const HITL_OPTIONS: { value: HitlMode; label: string; description: string }[] = [
  {
    value: "autopilot",
    label: "Autopilot",
    description: "Engine prunes and keeps candidates on its own.",
  },
  {
    value: "every_branch",
    label: "Review each branch",
    description: "Pause for your approval before every branch continues.",
  },
];

type DecideMode = "threshold" | "judge";

const DECIDE_OPTIONS: { value: DecideMode; label: string; description: string }[] = [
  {
    value: "threshold",
    label: "Threshold",
    description: "Deterministic score cutoff to prune candidates.",
  },
  {
    value: "judge",
    label: "LLM judge",
    description: "LLM comparatively decides which candidates to keep.",
  },
];

export function NewSessionDialog() {
  const router = useRouter();
  const refreshSidebar = useSessionStore((s) => s.refreshSidebar);

  const [open, setOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [title, setTitle] = useState("");
  const [model, setModel] = useState(SETTINGS_DEFAULT);
  const [maxDepth, setMaxDepth] = useState<number>(3);
  const [branchModels, setBranchModels] = useState<string[]>([]);
  const [hitlMode, setHitlMode] = useState<HitlMode>("autopilot");
  const [decideMode, setDecideMode] = useState<DecideMode>("threshold");
  const [budget, setBudget] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setGoal("");
    setTitle("");
    setModel(SETTINGS_DEFAULT);
    setMaxDepth(3);
    setBranchModels([]);
    setHitlMode("autopilot");
    setDecideMode("threshold");
    setBudget("");
    setError(null);
    setSubmitting(false);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Fill holes (a user may set branch 2 without branch 1) so the payload
      // is dense strings, not a sparse array that serializes nulls.
      const filledBranchModels = Array.from(
        { length: BRANCH_SLOTS },
        (_, i) => branchModels[i] ?? "",
      );
      const { session_id } = await api.createSession({
        goal,
        title: title.trim() ? title.trim() : null,
        config: {
          model: model === SETTINGS_DEFAULT ? null : model,
          branching_factor: 3,
          branch_models: filledBranchModels.some((m) => m !== "") ? filledBranchModels : null,
          max_depth: maxDepth,
          temperature: 0.7,
          hitl_mode: hitlMode,
          decide_mode: decideMode,
          budget_usd: budget.trim() === "" ? null : Number(budget),
        },
      });
      refreshSidebar();
      setOpen(false);
      reset();
      router.push(`/s/${session_id}`);
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button>New session</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New session</DialogTitle>
            <DialogDescription>
              Describe the goal you want to explore. Kodoku will seed the root
              node from it; the engine will branch into candidates once you
              click &quot;Run&quot; on the session page.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="goal">Goal</Label>
            <Textarea
              id="goal"
              required
              minLength={10}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. Brainstorm side-project ideas combining AI and music."
              rows={4}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="title">Title (optional)</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Auto-derived from goal if blank"
              maxLength={200}
            />
          </div>

          <div className="space-y-2">
            <Label>Model</Label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SETTINGS_DEFAULT}>
                  Settings default (recommended)
                </SelectItem>
                {MODEL_PRESETS.map((preset) => (
                  <SelectItem key={preset.value} value={preset.value}>
                    {preset.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Used to expand ideas. Scoring and synthesis always use the models
              from Settings.
            </p>
          </div>

          <div className="space-y-2">
            <Label>Exploration</Label>
            <div className="inline-flex w-full rounded-md border border-input p-0.5">
              {DEPTH_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setMaxDepth(option.value)}
                  aria-pressed={maxDepth === option.value}
                  className={cn(
                    "flex-1 rounded-[5px] px-2.5 py-1.5 text-sm font-medium transition-colors",
                    maxDepth === option.value
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {DEPTH_OPTIONS.find((option) => option.value === maxDepth)?.description}
            </p>
          </div>

          <div className="space-y-2">
            <Label>Per-branch models (optional)</Label>
            {Array.from({ length: BRANCH_SLOTS }).map((_, i) => (
              <select
                key={i}
                value={branchModels[i] ?? ""}
                onChange={(e) => {
                  const next = [...branchModels];
                  next[i] = e.target.value;
                  setBranchModels(next);
                }}
                className="w-full rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
              >
                <option value="">{`Branch ${i + 1}: session default`}</option>
                {MODEL_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
            ))}
          </div>

          <div className="space-y-2">
            <Label>Human review</Label>
            <div className="inline-flex w-full rounded-md border border-input p-0.5">
              {HITL_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setHitlMode(option.value)}
                  aria-pressed={hitlMode === option.value}
                  className={cn(
                    "flex-1 rounded-[5px] px-2.5 py-1.5 text-sm font-medium transition-colors",
                    hitlMode === option.value
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {HITL_OPTIONS.find((option) => option.value === hitlMode)?.description}
            </p>
          </div>

          <div className="space-y-2">
            <Label>Decision mode</Label>
            <div className="inline-flex w-full rounded-md border border-input p-0.5">
              {DECIDE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setDecideMode(option.value)}
                  aria-pressed={decideMode === option.value}
                  className={cn(
                    "flex-1 rounded-[5px] px-2.5 py-1.5 text-sm font-medium transition-colors",
                    decideMode === option.value
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {DECIDE_OPTIONS.find((option) => option.value === decideMode)?.description}
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="budget">Budget (USD, optional)</Label>
            <Input
              id="budget"
              type="number"
              min="0"
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              placeholder="No cap"
            />
            <p className="text-xs text-muted-foreground">
              Stops the run when the session cost passes this amount.
            </p>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || goal.length < 10}>
              {submitting ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
