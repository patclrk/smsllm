import httpx2
import pytest

from smsllm.llm import ChatMessage, GenParams, get_adapter


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = "ok"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Records the outbound request and returns a canned response."""

    calls: list[dict] = []

    def __init__(self, payload):
        self._payload = payload

    def __call__(self, *args, **kwargs):  # instantiated as httpx2.AsyncClient(...)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        type(self).calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(self._payload)


@pytest.fixture
def fake_http(monkeypatch):
    def _install(payload):
        _FakeClient.calls = []
        monkeypatch.setattr(httpx2, "AsyncClient", _FakeClient(payload))
        return _FakeClient

    return _install


async def test_openai_compat_request_and_parse(fake_http):
    client = fake_http({"choices": [{"message": {"content": "  hi there  "}}]})
    adapter = get_adapter("openai_compat")
    out = await adapter.generate(
        [ChatMessage("user", "hello")],
        GenParams(model="gpt-x", api_key="k", base_url="https://api.test/v1",
                  system_prompt="be nice"),
    )
    assert out == "hi there"
    call = client.calls[0]
    assert call["url"] == "https://api.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["json"]["model"] == "gpt-x"
    assert call["json"]["messages"][0] == {"role": "system", "content": "be nice"}
    assert call["json"]["messages"][1] == {"role": "user", "content": "hello"}


async def test_anthropic_request_and_parse(fake_http):
    client = fake_http({"content": [{"type": "text", "text": "claude says hi"}]})
    adapter = get_adapter("anthropic")
    out = await adapter.generate(
        [ChatMessage("user", "hello")],
        GenParams(model="claude-x", api_key="ak", system_prompt="sys"),
    )
    assert out == "claude says hi"
    call = client.calls[0]
    assert call["url"].endswith("/messages")
    assert call["headers"]["x-api-key"] == "ak"
    assert call["json"]["system"] == "sys"  # top-level, not a message
    assert call["json"]["messages"] == [{"role": "user", "content": "hello"}]


async def test_gemini_request_and_parse(fake_http):
    client = fake_http(
        {"candidates": [{"content": {"parts": [{"text": "gemini hi"}]}}]}
    )
    adapter = get_adapter("gemini")
    out = await adapter.generate(
        [ChatMessage("assistant", "prev"), ChatMessage("user", "hello")],
        GenParams(model="gemini-x", api_key="gk", system_prompt="sys"),
    )
    assert out == "gemini hi"
    call = client.calls[0]
    assert call["url"].endswith("/models/gemini-x:generateContent")
    assert call["headers"]["x-goog-api-key"] == "gk"
    # 'assistant' is remapped to 'model' for Gemini.
    assert call["json"]["contents"][0]["role"] == "model"
    assert call["json"]["contents"][1]["role"] == "user"
    assert call["json"]["system_instruction"]["parts"][0]["text"] == "sys"
