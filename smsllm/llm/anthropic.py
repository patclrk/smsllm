"""Anthropic Messages API adapter.

Differs from the OpenAI schema: the system prompt is a top-level field (not a message),
auth uses ``x-api-key`` + ``anthropic-version``, and the reply text lives under
``content[].text``.
"""

from __future__ import annotations

import httpx2

from .base import ChatMessage, GenParams, LLMError

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


class AnthropicAdapter:
    name = "anthropic"

    async def generate(
        self, messages: list[ChatMessage], params: GenParams
    ) -> str:
        base_url = (params.base_url or DEFAULT_BASE_URL).rstrip("/")
        payload: dict = {
            "model": params.model,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **params.extra_body,
        }
        if params.system_prompt:
            payload["system"] = params.system_prompt

        headers = {
            "x-api-key": params.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            async with httpx2.AsyncClient(timeout=params.timeout_seconds) as client:
                resp = await client.post(
                    base_url + "/messages", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx2.HTTPStatusError as exc:
            raise LLMError(
                f"anthropic HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx2.HTTPError as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc

        try:
            parts = [
                block["text"]
                for block in data["content"]
                if block.get("type") == "text"
            ]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"anthropic unexpected response: {data!r:.300}") from exc
        if not parts:
            raise LLMError(f"anthropic returned no text: {data!r:.300}")
        return "".join(parts).strip()
