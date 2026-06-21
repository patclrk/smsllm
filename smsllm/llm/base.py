"""Shared types and the adapter interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

Role = Literal["user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class GenParams:
    """Everything an adapter needs to make one generation call.

    The API key is resolved (from its env-var reference) before reaching the adapter, so
    adapters never touch ``BotConfig`` or the environment directly.
    """

    model: str
    api_key: str
    base_url: str = ""
    system_prompt: str = ""
    max_tokens: int = 512
    temperature: float = 0.7
    timeout_seconds: float = 60.0
    extra_body: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    """Raised when a provider call fails (network, auth, bad response)."""


@runtime_checkable
class LLMAdapter(Protocol):
    name: str

    async def generate(
        self, messages: list[ChatMessage], params: GenParams
    ) -> str:
        """Return the assistant's reply text for the given conversation."""
        ...
