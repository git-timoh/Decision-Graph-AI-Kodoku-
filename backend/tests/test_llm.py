from __future__ import annotations

import json

import pytest

from kodoku.llm import FakeLLMClient, LLMClient


async def test_complete_returns_scripted_strings_in_order_and_records_calls() -> None:
    client = FakeLLMClient(completions=["first", "second"])

    first = await client.complete(system="sys-a", prompt="prompt-a")
    second = await client.complete(system="sys-b", prompt="prompt-b")

    assert first == "first"
    assert second == "second"
    assert client.calls == [("sys-a", "prompt-a"), ("sys-b", "prompt-b")]


async def test_complete_raises_when_exhausted() -> None:
    client = FakeLLMClient(completions=["only"])
    await client.complete(system="s", prompt="p")

    with pytest.raises(AssertionError, match="FakeLLMClient.complete exhausted"):
        await client.complete(system="s", prompt="p")


async def test_from_json_round_trips() -> None:
    obj = {"decision": "expand", "score": 7}
    client = FakeLLMClient.from_json([obj])

    result = await client.complete(system="s", prompt="p", json_object=True)

    assert json.loads(result) == obj


async def test_stream_yields_chunks_in_order() -> None:
    client = FakeLLMClient(chunks=["he", "llo"])

    collected = [chunk async for chunk in client.stream(system="s", prompt="p")]

    assert collected == ["he", "llo"]


def test_fake_llm_client_satisfies_llm_client_protocol() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)
