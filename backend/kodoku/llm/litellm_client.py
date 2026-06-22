"""LiteLLM-backed `LLMClient` — talks to whatever provider `model` resolves to.

ponytail: unverified against a live provider this session (no real API calls
were made; behaviour against an actual model endpoint is untested).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import litellm
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.utils import ModelResponse


class LiteLLMClient:
    """`LLMClient` implementation backed by `litellm.acompletion`."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        self.api_base = api_base

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
        )
        result = cast(ModelResponse, response)
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
            api_key=self.api_key,
            api_base=self.api_base,
        )
        stream = cast(CustomStreamWrapper, response)
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
