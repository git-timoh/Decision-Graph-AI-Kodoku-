from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.llm.factory import DEFAULT_MODELS, RoleClients, make_role_clients, provider_of
from kodoku.llm.litellm_client import LiteLLMClient
from kodoku.repo.settings import SettingsRepository


@pytest.mark.asyncio
async def test_make_role_clients_uses_configured_models_and_stored_keys(
    db_session: AsyncSession,
) -> None:
    repo = SettingsRepository(db_session)
    await repo.upsert(
        {
            "model.expand": "anthropic/claude-sonnet-4-6",
            "model.evaluate": "deepseek/deepseek-chat",
            "model.synthesize": "openrouter/zhipu/glm-4",
            "key.anthropic": "sk-ant-stored",
            "key.deepseek": "sk-deepseek-stored",
            "key.openrouter": "sk-or-stored",
        }
    )

    clients = await make_role_clients(repo)

    assert isinstance(clients, RoleClients)

    assert isinstance(clients.expand, LiteLLMClient)
    assert clients.expand.model == "anthropic/claude-sonnet-4-6"
    assert clients.expand.api_key == "sk-ant-stored"

    assert isinstance(clients.evaluate, LiteLLMClient)
    assert clients.evaluate.model == "deepseek/deepseek-chat"
    assert clients.evaluate.api_key == "sk-deepseek-stored"

    assert isinstance(clients.synthesize, LiteLLMClient)
    assert clients.synthesize.model == "openrouter/zhipu/glm-4"
    assert clients.synthesize.api_key == "sk-or-stored"


@pytest.mark.asyncio
async def test_make_role_clients_resolves_ollama_base_url(db_session: AsyncSession) -> None:
    repo = SettingsRepository(db_session)
    await repo.upsert(
        {
            "model.expand": "ollama/llama3",
            "ollama.base_url": "http://localhost:11434",
        }
    )

    clients = await make_role_clients(repo)

    assert isinstance(clients.expand, LiteLLMClient)
    assert clients.expand.model == "ollama/llama3"
    assert clients.expand.api_base == "http://localhost:11434"
    assert clients.expand.api_key is None


@pytest.mark.asyncio
async def test_make_role_clients_falls_back_to_env_var_when_no_stored_key(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    repo = SettingsRepository(db_session)
    await repo.upsert({"model.evaluate": "deepseek/deepseek-chat"})

    clients = await make_role_clients(repo)

    assert isinstance(clients.evaluate, LiteLLMClient)
    assert clients.evaluate.api_key == "sk-from-env"


@pytest.mark.asyncio
async def test_make_role_clients_stored_key_takes_priority_over_env(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    repo = SettingsRepository(db_session)
    await repo.upsert(
        {
            "model.evaluate": "deepseek/deepseek-chat",
            "key.deepseek": "sk-from-store",
        }
    )

    clients = await make_role_clients(repo)

    assert isinstance(clients.evaluate, LiteLLMClient)
    assert clients.evaluate.api_key == "sk-from-store"


@pytest.mark.asyncio
async def test_make_role_clients_no_key_anywhere_leaves_api_key_none(
    db_session: AsyncSession,
) -> None:
    repo = SettingsRepository(db_session)
    await repo.upsert({"model.synthesize": "openai/gpt-4o-mini"})

    clients = await make_role_clients(repo)

    assert isinstance(clients.synthesize, LiteLLMClient)
    assert clients.synthesize.api_key is None


@pytest.mark.asyncio
async def test_make_role_clients_unset_role_model_uses_default(
    db_session: AsyncSession,
) -> None:
    repo = SettingsRepository(db_session)

    clients = await make_role_clients(repo)

    assert isinstance(clients.expand, LiteLLMClient)
    assert isinstance(clients.evaluate, LiteLLMClient)
    assert isinstance(clients.synthesize, LiteLLMClient)
    assert clients.expand.model == DEFAULT_MODELS["expand"]
    assert clients.evaluate.model == DEFAULT_MODELS["evaluate"]
    assert clients.synthesize.model == DEFAULT_MODELS["synthesize"]


@pytest.mark.parametrize(
    ("model", "expected_provider"),
    [
        ("deepseek/deepseek-chat", "deepseek"),
        ("openrouter/zhipu/glm-4", "openrouter"),
        ("anthropic/claude-sonnet-4-6", "anthropic"),
        ("openai/gpt-4o-mini", "openai"),
        ("zhipu/glm-4", "zhipu"),
        ("google/gemini-2.0-flash", "google"),
        ("ollama/llama3", "ollama"),
    ],
)
def test_provider_of_parses_prefix_before_first_slash(model: str, expected_provider: str) -> None:
    assert provider_of(model) == expected_provider


def test_build_client_for_model_resolves_key() -> None:
    from kodoku.llm.factory import build_client_for_model

    client = build_client_for_model("deepseek/deepseek-chat", {"key.deepseek": "sk-test"})
    assert isinstance(client, LiteLLMClient)
    assert client.model == "deepseek/deepseek-chat"
    assert client.api_key == "sk-test"


def test_build_client_for_model_ollama_uses_base_url() -> None:
    from kodoku.llm.factory import build_client_for_model

    client = build_client_for_model("ollama/llama3", {"ollama.base_url": "http://localhost:11434"})
    assert isinstance(client, LiteLLMClient)
    assert client.api_base == "http://localhost:11434"
    assert client.api_key is None
