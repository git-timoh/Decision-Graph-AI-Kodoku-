"""Production `LLMClient` factory, exposed as a FastAPI dependency.

Tests override the `get_llm_factory` dependency to inject a `FakeLLMClient`
instead of talking to a real provider via LiteLLM.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kodoku.llm.base import LLMClient
from kodoku.llm.litellm_client import LiteLLMClient


def make_llm_client(config: dict[str, Any]) -> LLMClient:
    """Build a `LiteLLMClient` from a session's `config` dict."""
    return LiteLLMClient(model=config["model"], temperature=config.get("temperature", 0.7))


def get_llm_factory() -> Callable[[dict[str, Any]], LLMClient]:
    """FastAPI dependency: returns the production client factory."""
    return make_llm_client
