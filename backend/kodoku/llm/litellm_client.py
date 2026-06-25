"""LiteLLM-backed `LLMClient` — talks to whatever provider `model` resolves to.

ponytail: unverified against a live provider this session (no real API calls
were made; behaviour against an actual model endpoint is untested).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import litellm
from litellm import completion_cost
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.utils import ModelResponse


class LiteLLMClient:
    """`LLMClient` implementation backed by `litellm.acompletion`."""

    #: Per-request wall-clock cap (seconds). Without it a hung or slow provider
    #: stalls the whole run indefinitely, since the engine awaits each call.
    DEFAULT_TIMEOUT = 120.0

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        self.api_base = api_base
        self.timeout = timeout
        self.cost_usd = 0.0

    async def complete(self, *, system: str, prompt: str, json_object: bool = False) -> str:
        response = await litellm.acompletion(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"} if json_object else None,
            api_key=self.api_key,
            api_base=self.api_base,
            timeout=self.timeout,
        )
        result = cast(ModelResponse, response)
        # ponytail: best-effort — completion_cost raises for models it has no
        # pricing for; a costless call must never break completion.
        try:
            self.cost_usd += completion_cost(completion_response=result)
        except Exception:  # noqa: BLE001
            pass
        return result.choices[0].message.content or ""

    async def stream(self, *, system: str, prompt: str) -> AsyncIterator[str]:
        response = await litellm.acompletion(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            stream=True,
            stream_options={"include_usage": True},
            api_key=self.api_key,
            api_base=self.api_base,
            timeout=self.timeout,
        )
        stream = cast(CustomStreamWrapper, response)
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                # ponytail: best-effort streaming cost; providers that omit
                # usage in the final chunk leave synthesis cost at 0.
                try:
                    self.cost_usd += completion_cost(
                        completion_response=chunk, model=self.model
                    )
                except Exception:  # noqa: BLE001
                    pass
