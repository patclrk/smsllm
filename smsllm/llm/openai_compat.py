"""OpenAI-compatible adapter (the default).

Speaks the OpenAI ``/v1/chat/completions`` schema, which is shared by OpenAI, OpenRouter,
Together, Groq, Fireworks, and local runtimes (Ollama, vLLM, LM Studio). New providers in
this family need only a ``BotConfig`` row (base_url + model + key), no code.
"""

from __future__ import annotations

import httpx2

from .base import ChatMessage, GenParams, LLMError


class OpenAICompatAdapter:
    name = "openai_compat"

    async def generate(
        self, messages: list[ChatMessage], params: GenParams
    ) -> str:
        payload: dict = {
            "model": params.model,
            "messages": _build_messages(messages, params.system_prompt),
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            **params.extra_body,
        }
        url = params.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {params.api_key}"}

        try:
            async with httpx2.AsyncClient(timeout=params.timeout_seconds) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx2.HTTPStatusError as exc:
            raise LLMError(
                f"openai_compat HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx2.HTTPError as exc:
            raise LLMError(f"openai_compat request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMError(f"openai_compat unexpected response: {data!r:.300}") from exc


def _build_messages(messages: list[ChatMessage], system_prompt: str) -> list[dict]:
    out: list[dict] = []
    if system_prompt:
        out.append({"role": "system", "content": system_prompt})
    out.extend({"role": m.role, "content": m.content} for m in messages)
    return out
