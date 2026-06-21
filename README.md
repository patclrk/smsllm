# smsllm

Converse with an LLM over SMS. A person texts a Twilio number; `smsllm` buffers their
messages, waits a configurable quiet period for follow-ups, sends the batch to that
number's configured LLM, and texts the reply back. Each Twilio number maps to its own LLM
("bot"), so you can run different models / prompts on different numbers.

## How it works

```
Inbound SMS -> Twilio webhook (POST /sms) -> buffer per (number, sender)
            -> debounce timer (default 5 min, resets on each new message)
            -> background worker dispatches the batch to the bot's LLM
            -> reply trimmed to a length budget -> sent back via Twilio
```

State (message buffers, timers, the global usage counter) is persisted, so a restart
mid-wait doesn't drop a conversation.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A Twilio account + SMS-capable number
- An API key for at least one LLM provider

## Setup

```sh
uv sync                      # create the venv and install deps
cp .env.example .env         # fill in Twilio creds + global caps
uv run smsllm initdb         # create the SQLite tables
```

Register a bot (one Twilio number -> one LLM config):

```sh
export OPENAI_API_KEY=sk-...
uv run smsllm add-bot \
  --number +15555550123 \
  --adapter openai_compat \
  --base-url https://api.openai.com/v1 \
  --model gpt-4o-mini \
  --api-key-ref OPENAI_API_KEY \
  --system-prompt "You are a helpful assistant. Keep replies short."
```

The `--api-key-ref` is the *name* of an env var holding the key — the raw key is never
stored in the database.

## Run

```sh
uv run uvicorn smsllm.main:app --reload   # serves POST /sms and runs the worker
```

Expose it publicly (e.g. `ngrok http 8000`) and point your Twilio number's Messaging
webhook at `https://<host>/sms`. Set `PUBLIC_BASE_URL` in `.env` to that exact URL so
Twilio signature validation passes.

## Supported LLM providers

The `openai_compat` adapter speaks the OpenAI `/v1/chat/completions` schema, so it covers
OpenAI, OpenRouter, Together, Groq, Fireworks, and local runtimes (Ollama, vLLM, …) — just
change `--base-url`/`--model`. Dedicated adapters exist for `anthropic` (Messages API) and
`gemini` (Google `generateContent`).

## Abuse / cost protection

- **Per-sender cap** (`--max-messages-per-sender`, per bot): bounds how many of one
  sender's buffered messages are forwarded to the LLM per dispatch.
- **Global call cap** (`.env`): `GLOBAL_MAX_LLM_CALLS_TOTAL` is an absolute ceiling;
  `GLOBAL_MAX_LLM_CALLS_PER_WINDOW` + `GLOBAL_WINDOW_SECONDS` add a rolling rate cap so the
  service resets during normal operation.

## Tests

```sh
uv run pytest
```
