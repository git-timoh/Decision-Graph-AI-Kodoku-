"""In-memory `LLMClient` for tests — no network calls."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


class FakeLLMClient:
    """Scripted `LLMClient` implementation.

    `complete` pops responses off `completions` in order (FIFO); `stream`
    yields `chunks` in order. Every `complete` call is recorded in `self.calls`
    for assertions in step/engine tests.
    """

    def __init__(
        self,
        completions: list[str] | None = None,
        chunks: list[str] | None = None,
        model: str = "fake",
        cost_per_call: float = 0.0,
    ) -> None:
        self.model = model
        self.completions: list[str] = list(completions) if completions is not None else []
        self.chunks: list[str] = list(chunks) if chunks is not None else [""]
        self.calls: list[tuple[str, str]] = []
        self.cost_per_call = cost_per_call
        self.cost_usd = 0.0

    async def complete(self, *, system: str, prompt: str, json_object: bool = False) -> str:
        self.calls.append((system, prompt))
        self.cost_usd += self.cost_per_call
        if not self.completions:
            raise AssertionError("FakeLLMClient.complete exhausted")
        return self.completions.pop(0)

    async def stream(self, *, system: str, prompt: str) -> AsyncIterator[str]:
        for chunk in self.chunks:
            yield chunk

    @classmethod
    def from_json(cls, objs: list[dict[str, Any]]) -> FakeLLMClient:
        """Build a client whose `completions` are the JSON-dumped objects, in order."""
        return cls(completions=[json.dumps(obj) for obj in objs])
