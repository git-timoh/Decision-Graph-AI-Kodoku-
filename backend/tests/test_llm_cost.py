"""Cost accrual on LLM clients. Live providers are never called here."""
from __future__ import annotations

import pytest

from kodoku.llm.base import LLMClient
from kodoku.llm.fake import FakeLLMClient
from kodoku.llm.litellm_client import LiteLLMClient


@pytest.mark.asyncio
async def test_fake_accrues_cost_per_call() -> None:
    llm = FakeLLMClient(completions=["a", "b"], cost_per_call=0.01)
    assert llm.cost_usd == 0.0
    await llm.complete(system="s", prompt="p")
    assert llm.cost_usd == pytest.approx(0.01)
    await llm.complete(system="s", prompt="p")
    assert llm.cost_usd == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_fake_default_cost_is_zero() -> None:
    llm = FakeLLMClient(completions=["a"])
    await llm.complete(system="s", prompt="p")
    assert llm.cost_usd == 0.0


def test_clients_satisfy_protocol() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)
    assert isinstance(LiteLLMClient(model="anthropic/claude-sonnet-4-6"), LLMClient)
    assert LiteLLMClient(model="x").cost_usd == 0.0
