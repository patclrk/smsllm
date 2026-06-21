"""Google Gemini adapter (``generateContent``).

Roles are ``user`` / ``model`` (not ``assistant``), messages are ``contents`` with
``parts``, the system prompt is ``system_instruction``, and the key is passed as a query
param. Reply text is under ``candidates[].content.parts[].text``.
"""

from __future__ import annotations

import httpx2

from .base import ChatMessage, GenParams, LLMError

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiAdapter:
    name = "gemini"

    async def generate(
        self, messages: list[ChatMessage], params: GenParams
    ) -> str:
        base_url = (params.base_url or DEFAULT_BASE_URL).rstrip("/")
        contents = [
            {
                "role": "model" if m.role == "assistant" else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
        ]
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": params.max_tokens,
                "temperature": params.temperature,
            },
            **params.extra_body,
        }
        if params.system_prompt:
            payload["system_instruction"] = {"parts": [{"text": params.system_prompt}]}

        url = f"{base_url}/models/{params.model}:generateContent"
        headers = {"x-goog-api-key": params.api_key, "content-type": "application/json"}

        try:
            async with httpx2.AsyncClient(timeout=params.timeout_seconds) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx2.HTTPStatusError as exc:
            raise LLMError(
                f"gemini HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx2.HTTPError as exc:
            raise LLMError(f"gemini request failed: {exc}") from exc

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"gemini unexpected response: {data!r:.300}") from exc
        if not text:
            raise LLMError(f"gemini returned no text: {data!r:.300}")
        return text.strip()
