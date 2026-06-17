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
    """

    async def complete(self, *, system: str, prompt: str, json_object: bool = False) -> str: ...

    def stream(self, *, system: str, prompt: str) -> AsyncIterator[str]: ...
