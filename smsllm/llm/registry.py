"""Maps a ``BotConfig.adapter`` string to an adapter instance."""

from __future__ import annotations

from .anthropic import AnthropicAdapter
from .base import LLMAdapter
from .gemini import GeminiAdapter
from .openai_compat import OpenAICompatAdapter

_ADAPTERS: dict[str, LLMAdapter] = {
    OpenAICompatAdapter.name: OpenAICompatAdapter(),
    AnthropicAdapter.name: AnthropicAdapter(),
    GeminiAdapter.name: GeminiAdapter(),
}


def get_adapter(name: str) -> LLMAdapter:
    try:
        return _ADAPTERS[name]
    except KeyError:
        raise ValueError(
            f"unknown adapter {name!r}; available: {sorted(_ADAPTERS)}"
        ) from None


def available_adapters() -> list[str]:
    return sorted(_ADAPTERS)
