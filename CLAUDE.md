# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`smsllm` lets a person text a Twilio number and converse with an LLM over SMS. Each Twilio
number maps to its own LLM config ("bot"), so different numbers can run different
models/prompts. See `README.md` for the user-facing setup walkthrough.

## Commands

This project is managed with **uv**. Use **httpx2** (not httpx) for any HTTP to providers.

```sh
uv sync                       # create venv + install deps (including dev group)
uv run pytest                 # run the whole test suite
uv run pytest tests/test_limits.py::test_window_cap_resets_after_window   # single test
uv run smsllm initdb          # create SQLite tables
uv run smsllm add-bot --number +1555... --base-url ... --model ... --api-key-ref OPENAI_API_KEY
uv run smsllm list-bots
uv run uvicorn smsllm.main:app --reload   # serve POST /sms + run the worker
```

There is no linter/formatter configured. `pytest` is set to `asyncio_mode = "auto"`, so
`async def test_*` functions run without an explicit marker.

## Architecture

The flow is **inbound webhook → buffer → debounce timer → background worker → LLM → reply**,
deliberately decoupled so the HTTP request returns immediately and the (possibly slow) LLM
call happens later, out of band.

- **Ingestion (`main.py`, `twilio_client.py`, `buffer.py`)** — `POST /sms` validates the
  Twilio signature, finds the `BotConfig` for the `To` number, and calls
  `buffer.record_inbound`, which appends the message to the sender's *open* `Conversation`
  and pushes `fire_at` out to `now + debounce_seconds`. It returns empty TwiML; **no reply
  is sent here**.
- **Worker (`worker.py`)** — started in `main.py`'s lifespan, polls every
  `worker_poll_seconds` for conversations where `status='open' AND fire_at <= now`. It
  claims each via an atomic `open → processing` UPDATE (`_claim`, checks `rowcount`) so a
  late message starts a *fresh* open conversation instead of racing the in-flight one, then
  calls `dispatch_conversation`.
- **Dispatch (`dispatch.py`)** — three phases, and the key invariant is **no DB session is
  held across the `await` on the LLM**: phase 1 (sync) loads config + messages, enforces
  caps, and captures a plain `_Plan`; phase 2 (async) calls the provider; phase 3 (sync)
  records usage, sends SMS (`asyncio.to_thread`, since the Twilio SDK is blocking), persists
  the reply, and sets `status='done'` (or `'skipped'`/`'error'`).
- **LLM adapters (`llm/`)** — thin `LLMAdapter` protocol (`base.py`); `registry.get_adapter`
  maps a `BotConfig.adapter` string to an instance. `openai_compat` is the **default** and
  covers most providers (OpenAI/OpenRouter/Together/Groq/Ollama/vLLM…) via config alone —
  adding such a provider needs **only a `BotConfig` row, no code**. `anthropic` and `gemini`
  exist for their distinct schemas. To add a non-OpenAI-shaped provider, add an adapter and
  register it.

## Conventions and gotchas

- **Datetimes are naive-UTC everywhere.** `models.utcnow()` returns naive UTC and
  `models.as_naive_utc()` normalizes inputs. This is intentional: SQLite does not preserve
  tzinfo, and mixing aware/naive datetimes silently breaks `==`/`<` comparisons. Any new
  code touching `fire_at`/`window_start`/timestamps must stay naive-UTC.
- **Per-bot settings live in `BotConfig`** (model, prompt, debounce, length budget,
  `max_messages_per_sender`, etc.); **process-wide settings live in `config.Settings`**
  (Twilio creds, DB URL, worker cadence, the global LLM-call cap). Don't put per-bot config
  in `Settings` or vice versa.
- **API keys are never stored in the DB.** `BotConfig.api_key_ref` holds the *name* of an
  env var; `dispatch.py` resolves it with `os.environ.get` at call time.
- **Two independent abuse guards (`limits.py`).** (1) Per-sender cap: `select_recent` keeps
  only the most recent N of a sender's buffered messages per dispatch. (2) Global call cap:
  `check_global_cap` (absolute ceiling + optional rolling window) is checked *before* the
  call; `record_call` increments the persisted `UsageCounter` *only on success*. The counter
  is best-effort under multiple concurrent workers (fine for single-process SQLite).
- **Reply length budget (`formatting.py`)** is enforced twice: as a prompt instruction
  (`budget_instruction`) and as a hard post-process net (`enforce`, `split` vs `truncate`).
  SMS is really 160/70 chars and Twilio auto-segments — the budget is a cost/UX knob.

## Tests

`tests/conftest.py` sets `DATABASE_URL` to a throwaway SQLite file and disables signature
validation **before any smsllm import** (db.py builds its engine at import time), and resets
tables around each test. Adapters and Twilio send are mocked by monkeypatching
`smsllm.dispatch.get_adapter` / `smsllm.dispatch.send_sms` (see `test_dispatch.py`); HTTP is
mocked by patching `httpx2.AsyncClient` (see `test_adapters.py`).
