"""REST API for app-wide settings: BYOK provider keys, Ollama base URL, and
per-role model choices.

Provider keys are secrets and are never returned in full — `GET` only ever
exposes whether a key is set and a 4-character hint.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import (
    MODEL_ROLES,
    PROVIDER_NAMES,
    ProviderStatus,
    SettingsResponse,
    SettingsTestResponse,
    SettingsUpdate,
)
from kodoku.db.session import get_db
from kodoku.llm.factory import RoleClients, make_role_clients
from kodoku.repo.settings import SettingsRepository

router = APIRouter(prefix="/settings", tags=["settings"])

#: Builds the per-role LLM clients to connection-test against, given the
#: request's DB session. Overridden in tests to inject a `RoleClients` of
#: fakes so `/settings/test` never makes a real network call.
RoleClientsBuilder = Callable[[AsyncSession], Awaitable[RoleClients]]


async def _default_role_clients(s: AsyncSession) -> RoleClients:
    return await make_role_clients(SettingsRepository(s))


def get_role_clients_builder() -> RoleClientsBuilder:
    """FastAPI dependency: returns the production role-clients builder."""
    return _default_role_clients


_HINT_LEN = 4


def _provider_key(name: str) -> str:
    return f"key.{name}"


def _model_key(role: str) -> str:
    return f"model.{role}"


_OLLAMA_KEY = "ollama.base_url"


def _repo(db: AsyncSession = Depends(get_db)) -> SettingsRepository:  # noqa: B008
    return SettingsRepository(db)


def _to_response(raw: dict[str, str]) -> SettingsResponse:
    providers: dict[str, ProviderStatus] = {}
    for name in PROVIDER_NAMES:
        value = raw.get(_provider_key(name))
        if value:
            hint = value[-_HINT_LEN:] if len(value) > _HINT_LEN else None
            providers[name] = ProviderStatus(set=True, hint=hint)
        else:
            providers[name] = ProviderStatus(set=False, hint=None)

    ollama_base_url = raw.get(_OLLAMA_KEY) or None

    models: dict[str, str | None] = {}
    for role in MODEL_ROLES:
        models[role] = raw.get(_model_key(role)) or None

    return SettingsResponse(providers=providers, ollama_base_url=ollama_base_url, models=models)


@router.get("", response_model=SettingsResponse)
async def read_settings(
    repo: SettingsRepository = Depends(_repo),  # noqa: B008
) -> SettingsResponse:
    raw = await repo.get_all()
    return _to_response(raw)


@router.put("", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    repo: SettingsRepository = Depends(_repo),  # noqa: B008
) -> SettingsResponse:
    items: dict[str, str] = {}

    if payload.providers is not None:
        for name, key in payload.providers.items():
            items[_provider_key(name)] = key if key is not None else ""

    if "ollama_base_url" in payload.model_fields_set:
        items[_OLLAMA_KEY] = payload.ollama_base_url or ""

    if payload.models is not None:
        for role, model in payload.models.items():
            items[_model_key(role)] = model

    await repo.upsert(items)

    raw = await repo.get_all()
    return _to_response(raw)


@router.post("/test", response_model=SettingsTestResponse)
async def test_settings(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    build_clients: RoleClientsBuilder = Depends(get_role_clients_builder),  # noqa: B008
) -> SettingsTestResponse:
    """Connection check: one tiny completion on the `evaluate` role client.

    Never raises — any failure (bad key, unreachable provider, etc.) is
    reported as `{ok: false, error: <message>}` rather than propagated, since
    this is a smoke check, not a critical endpoint. The error message comes
    from the provider's exception only; no stored key is ever included.
    """
    try:
        clients = await build_clients(db)
        await clients.evaluate.complete(system="ping", prompt="Reply with OK")
    except Exception as exc:  # noqa: BLE001 — surface any provider error verbatim
        return SettingsTestResponse(ok=False, error=str(exc))
    return SettingsTestResponse(ok=True, error=None)
