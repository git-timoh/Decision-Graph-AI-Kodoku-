"""Production `LLMClient` factory, exposed as a FastAPI dependency.

`make_role_clients` is the Phase A BYOK factory. It reads stored provider keys
and per-role model choices from `SettingsRepository` and builds one
`LiteLLMClient` per role (`expand`/`evaluate`/`synthesize`), resolving each
client's API key from the store (falling back to the matching provider env
var) and, for `ollama/*` models, the stored Ollama base URL.

`kodoku/api/run.py` calls this once per run; tests override the run router's
role-clients builder to inject a `RoleClients` of `FakeLLMClient`s instead of
talking to a real provider via LiteLLM.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kodoku.llm.base import LLMClient

if TYPE_CHECKING:
    from kodoku.repo.settings import SettingsRepository


# --- Phase A: per-role BYOK client factory -------------------------------

#: Default models per role: `expand` favours a strong model, `evaluate` and
#: `synthesize` favour a cheap one. Used when `model.<role>` is unset.
DEFAULT_MODELS: dict[str, str] = {
    "expand": "anthropic/claude-sonnet-4-6",
    "evaluate": "deepseek/deepseek-chat",
    "synthesize": "deepseek/deepseek-chat",
}

#: Provider name (as stored under `key.<provider>`) -> fallback env var.
#: The stored BYOK key is always tried first; this is only a best-effort
#: fallback for local/dev setups that configure providers via `.env`.
PROVIDER_ENV: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "google": "GEMINI_API_KEY",
}

_OLLAMA_PROVIDER = "ollama"
_OLLAMA_BASE_URL_KEY = "ollama.base_url"


@dataclass(frozen=True, slots=True)
class RoleClients:
    """One `LLMClient` per engine role, bound to its configured model + key."""

    expand: LLMClient
    evaluate: LLMClient
    synthesize: LLMClient


def provider_of(model: str) -> str:
    """The provider prefix of a LiteLLM-style model string.

    `"deepseek/deepseek-chat"` -> `"deepseek"`; `"openrouter/zhipu/glm-4"` ->
    `"openrouter"` (only the substring before the *first* `/`).
    """
    return model.split("/", 1)[0]


def _resolve_api_key(provider: str, settings: dict[str, str]) -> str | None:
    stored = settings.get(f"key.{provider}")
    if stored:
        return stored
    env_var = PROVIDER_ENV.get(provider)
    if env_var:
        return os.environ.get(env_var) or None
    return None


def build_client_for_model(
    model: str, settings: dict[str, str], temperature: float = 0.7
) -> LLMClient:
    """Build one `LLMClient` for an arbitrary model string, resolving its BYOK key."""
    from kodoku.llm.litellm_client import LiteLLMClient

    provider = provider_of(model)
    if provider == _OLLAMA_PROVIDER:
        api_key: str | None = None
        api_base = settings.get(_OLLAMA_BASE_URL_KEY) or None
    else:
        api_key = _resolve_api_key(provider, settings)
        api_base = None

    return LiteLLMClient(
        model=model, temperature=temperature, api_key=api_key, api_base=api_base
    )


def _build_client(role: str, settings: dict[str, str]) -> LLMClient:
    model = settings.get(f"model.{role}") or DEFAULT_MODELS[role]
    return build_client_for_model(model, settings)


async def make_role_clients(
    settings: SettingsRepository,
    *,
    expand_model: str | None = None,
    expand_temperature: float | None = None,
) -> RoleClients:
    """Build the per-role `LLMClient`s from stored BYOK keys + model choices.

    `expand_model`/`expand_temperature` override the expand role for one run
    (the session's model/temperature); evaluate and synthesize always use the
    Settings role models so scoring stays consistent across sessions.
    """
    raw = await settings.get_all()
    model = expand_model or raw.get("model.expand") or DEFAULT_MODELS["expand"]
    temperature = 0.7 if expand_temperature is None else expand_temperature
    return RoleClients(
        expand=build_client_for_model(model, raw, temperature=temperature),
        evaluate=_build_client("evaluate", raw),
        synthesize=_build_client("synthesize", raw),
    )
