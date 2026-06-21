"""Application settings, loaded from environment / .env.

Per-bot settings (model, prompt, debounce, length budget, per-sender cap) live in the
``BotConfig`` table, not here. This holds process-wide settings: Twilio credentials, the
database URL, the worker cadence, and the global LLM-call cap that protects the operator
from being flooded by external senders.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Twilio ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    # Public base URL the Twilio webhook is reachable at, used for signature validation
    # (must match exactly what Twilio is configured to POST to, including scheme + path).
    public_base_url: str = "http://localhost:8000"
    # Set False only for local testing without a real Twilio signature.
    validate_twilio_signature: bool = True

    # --- Storage ---
    database_url: str = "sqlite:///smsllm.db"

    # --- Worker ---
    worker_poll_seconds: float = 10.0

    # --- Defaults applied when creating a BotConfig (overridable per bot) ---
    default_debounce_seconds: int = 300
    default_length_budget_chars: int = 255
    default_max_messages_per_sender: int = 10

    # --- Global LLM-call cap (abuse / cost protection) ---
    # Absolute hard ceiling on total successful LLM calls across all numbers/senders.
    # 0 disables the absolute ceiling.
    global_max_llm_calls_total: int = 0
    # Optional rolling rate cap. When per_window > 0 and window_seconds > 0, no more than
    # ``per_window`` calls are allowed within any ``window_seconds`` bucket.
    global_max_llm_calls_per_window: int = 0
    global_window_seconds: int = 86_400


@lru_cache
def get_settings() -> Settings:
    return Settings()
