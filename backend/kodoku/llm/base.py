"""LLM client protocol shared by the fake and LiteLLM implementations."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface the engine needs from any LLM backend.

    `complete` returns the model's raw text; callers parse JSON themselves
    when `json_object=True`. `stream` is a *sync* method that returns an
    `AsyncIterator[str]`, so callers write `async for chunk in llm.stream(...)`.
    `model` is the model string this client is bound to (e.g. recorded on
    `Evaluation` rows). `cost_usd` is the cumulative USD cost of this client's
    calls (best-effort; 0.0 if the provider/model has no cost data).
    """

    model: str
    cost_usd: float

    async def complete(self, *, system: str, prompt: str, json_object: bool = False) -> str: ...

    def stream(self, *, system: str, prompt: str) -> AsyncIterator[str]: ...
