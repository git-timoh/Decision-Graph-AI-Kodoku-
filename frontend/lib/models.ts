/** Canonical model-preset list, shared by the new-session dialog and settings.
 *
 * The backend doesn't expose a preset catalog, so this is the single source of
 * truth on the frontend (previously duplicated and drifting across two files).
 * Slugs are LiteLLM-style `provider/model`. Settings also accepts a free-text
 * custom slug, so this list is a convenience shortlist, not a hard allowlist —
 * keep it small and known-good rather than exhaustive (OpenRouter slugs drift). */
export type ModelPreset = { value: string; label: string };

export const MODEL_PRESETS: ModelPreset[] = [
  { value: "anthropic/claude-sonnet-4-6", label: "Claude Sonnet 4.6 (recommended)" },
  { value: "openai/gpt-4o-mini", label: "OpenAI GPT-4o mini" },
  { value: "deepseek/deepseek-chat", label: "DeepSeek Chat (cheap)" },
  { value: "openrouter/deepseek/deepseek-chat", label: "OpenRouter: DeepSeek Chat" },
  { value: "ollama/llama3.1", label: "Ollama (local)" },
];
