"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, describeError } from "@/lib/api/client";
import { MODEL_PRESETS } from "@/lib/models";
import type { SettingsResponse, SettingsUpdate } from "@/lib/types/api";

const PROVIDERS = [
  { name: "openrouter", label: "OpenRouter" },
  { name: "deepseek", label: "DeepSeek" },
  { name: "openai", label: "OpenAI" },
  { name: "anthropic", label: "Anthropic" },
  { name: "zhipu", label: "Zhipu (GLM)" },
  { name: "google", label: "Google" },
] as const;

type ProviderName = (typeof PROVIDERS)[number]["name"];

const MODEL_ROLES = ["expand", "evaluate", "synthesize"] as const;
type ModelRole = (typeof MODEL_ROLES)[number];

const ROLE_LABELS: Record<ModelRole, string> = {
  expand: "Expand",
  evaluate: "Evaluate",
  synthesize: "Synthesize",
};


const CUSTOM_VALUE = "__custom__";

function providerOf(model: string): string {
  return model.split("/", 1)[0];
}

/** A model select is enabled if its provider's key is set, an OpenRouter key
 * covers everything, or it's an `ollama/*` model with a base URL configured. */
function isModelUsable(
  model: string,
  providersSet: Record<string, boolean>,
  ollamaBaseUrl: string,
): boolean {
  const provider = providerOf(model);
  if (provider === "ollama") return ollamaBaseUrl.trim().length > 0;
  if (providersSet[provider]) return true;
  return providersSet.openrouter ?? false;
}

type KeyFieldState = {
  /** Whether the user has typed a new value for this provider since load. */
  touched: boolean;
  /** The new value to send on save; empty string means "clear". */
  value: string;
};

function emptyKeyFields(): Record<ProviderName, KeyFieldState> {
  const fields = {} as Record<ProviderName, KeyFieldState>;
  for (const { name } of PROVIDERS) {
    fields[name] = { touched: false, value: "" };
  }
  return fields;
}

export function SettingsForm() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [keyFields, setKeyFields] = useState<Record<ProviderName, KeyFieldState>>(
    emptyKeyFields(),
  );
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("");
  const [models, setModels] = useState<Record<ModelRole, string>>({
    expand: "",
    evaluate: "",
    synthesize: "",
  });
  const [customModel, setCustomModel] = useState<Record<ModelRole, string>>({
    expand: "",
    evaluate: "",
    synthesize: "",
  });

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; error: string | null } | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    api
      .getSettings()
      .then((data) => {
        if (cancelled) return;
        setSettings(data);
        setOllamaBaseUrl(data.ollama_base_url ?? "");
        setModels({
          expand: data.models.expand ?? "",
          evaluate: data.models.evaluate ?? "",
          synthesize: data.models.synthesize ?? "",
        });
        setCustomModel({
          expand:
            data.models.expand && !MODEL_PRESETS.some((p) => p.value === data.models.expand)
              ? data.models.expand
              : "",
          evaluate:
            data.models.evaluate && !MODEL_PRESETS.some((p) => p.value === data.models.evaluate)
              ? data.models.evaluate
              : "",
          synthesize:
            data.models.synthesize &&
            !MODEL_PRESETS.some((p) => p.value === data.models.synthesize)
              ? data.models.synthesize
              : "",
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const providersSet: Record<string, boolean> = useMemo(() => {
    const result: Record<string, boolean> = {};
    for (const { name } of PROVIDERS) {
      const pendingClear = keyFields[name].touched && keyFields[name].value === "";
      const pendingSet = keyFields[name].touched && keyFields[name].value !== "";
      const currentlySet = settings?.providers[name]?.set ?? false;
      result[name] = pendingSet || (currentlySet && !pendingClear);
    }
    return result;
  }, [settings, keyFields]);

  function setKeyField(name: ProviderName, value: string) {
    setKeyFields((prev) => ({ ...prev, [name]: { touched: true, value } }));
  }

  function clearKeyField(name: ProviderName) {
    setKeyFields((prev) => ({ ...prev, [name]: { touched: true, value: "" } }));
  }

  function selectedPresetValue(role: ModelRole): string {
    const current = models[role];
    if (!current) return "";
    if (MODEL_PRESETS.some((p) => p.value === current)) return current;
    return CUSTOM_VALUE;
  }

  function handlePresetChange(role: ModelRole, value: string) {
    if (value === CUSTOM_VALUE) {
      setModels((prev) => ({ ...prev, [role]: customModel[role] }));
    } else {
      setModels((prev) => ({ ...prev, [role]: value }));
    }
  }

  function handleCustomModelChange(role: ModelRole, value: string) {
    setCustomModel((prev) => ({ ...prev, [role]: value }));
    setModels((prev) => ({ ...prev, [role]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaveOk(false);
    setTestResult(null);
    try {
      const body: SettingsUpdate = {
        providers: Object.fromEntries(
          PROVIDERS.filter(({ name }) => keyFields[name].touched).map(({ name }) => [
            name,
            keyFields[name].value === "" ? null : keyFields[name].value,
          ]),
        ),
        ollama_base_url: ollamaBaseUrl.trim() ? ollamaBaseUrl.trim() : null,
        models: Object.fromEntries(
          MODEL_ROLES.filter((role) => models[role].trim() !== "").map((role) => [
            role,
            models[role].trim(),
          ]),
        ),
      };
      const updated = await api.putSettings(body);
      setSettings(updated);
      setKeyFields(emptyKeyFields());
      setSaveOk(true);
    } catch (err) {
      setSaveError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testSettings();
      setTestResult({ ok: result.ok, error: result.error ?? null });
    } catch (err) {
      setTestResult({ ok: false, error: describeError(err) });
    } finally {
      setTesting(false);
    }
  }

  if (loadError) {
    return <p className="text-sm text-destructive">Backend unreachable: {loadError}</p>;
  }

  if (!settings) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="max-w-2xl space-y-8">
      <section className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Provider keys</h2>
          <p className="text-xs text-muted-foreground">
            Keys are stored server-side and never displayed in full — only the last
            4 characters are shown once saved.
          </p>
        </div>
        <div className="space-y-4">
          {PROVIDERS.map(({ name, label }) => {
            const status = settings.providers[name];
            const field = keyFields[name];
            return (
              <div key={name} className="space-y-2">
                <Label htmlFor={`key-${name}`}>{label}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id={`key-${name}`}
                    type="password"
                    autoComplete="off"
                    value={field.value}
                    onChange={(e) => setKeyField(name, e.target.value)}
                    placeholder={
                      status?.set && status.hint
                        ? `Saved key ending in ${status.hint} — paste to replace`
                        : status?.set
                          ? "Saved key — paste to replace"
                          : "Paste API key"
                    }
                  />
                  {(status?.set || field.touched) && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => clearKeyField(name)}
                    >
                      Clear
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="space-y-2">
        <Label htmlFor="ollama-base-url">Ollama base URL</Label>
        <Input
          id="ollama-base-url"
          value={ollamaBaseUrl}
          onChange={(e) => setOllamaBaseUrl(e.target.value)}
          placeholder="http://localhost:11434"
        />
        <p className="text-xs text-muted-foreground">
          Required to enable any <code>ollama/*</code> model below.
        </p>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Models per role</h2>
          <p className="text-xs text-muted-foreground">
            A model is selectable once its provider has a key (or an OpenRouter key,
            which covers every model), or it&apos;s an Ollama model with a base URL set.
          </p>
        </div>
        <div className="space-y-4">
          {MODEL_ROLES.map((role) => {
            const usable = models[role]
              ? isModelUsable(models[role], providersSet, ollamaBaseUrl)
              : true;
            const provider = models[role] ? providerOf(models[role]) : null;
            const isCustom = selectedPresetValue(role) === CUSTOM_VALUE;
            return (
              <div key={role} className="space-y-2">
                <Label>{ROLE_LABELS[role]}</Label>
                <Select
                  value={selectedPresetValue(role)}
                  onValueChange={(value) => handlePresetChange(role, value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a model" />
                  </SelectTrigger>
                  <SelectContent>
                    {MODEL_PRESETS.map((preset) => (
                      <SelectItem key={preset.value} value={preset.value}>
                        {preset.label}
                      </SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_VALUE}>Custom…</SelectItem>
                  </SelectContent>
                </Select>
                {isCustom && (
                  <Input
                    value={customModel[role]}
                    onChange={(e) => handleCustomModelChange(role, e.target.value)}
                    placeholder="e.g. openrouter/mistralai/mistral-large"
                  />
                )}
                {models[role] && !usable && provider && (
                  <p className="text-xs text-amber-600">
                    Add a key for {provider === "ollama" ? "Ollama (base URL)" : provider} to use
                    this model.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {saveError && <p className="text-sm text-destructive">{saveError}</p>}
      {saveOk && <p className="text-sm text-emerald-600">Settings saved.</p>}
      {testResult && (
        <p className={testResult.ok ? "text-sm text-emerald-600" : "text-sm text-destructive"}>
          {testResult.ok ? "Connection OK." : testResult.error}
        </p>
      )}

      <div className="flex gap-2">
        <Button type="button" variant="outline" onClick={handleTest} disabled={testing}>
          {testing ? "Testing…" : "Test connection"}
        </Button>
        <Button type="button" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}
