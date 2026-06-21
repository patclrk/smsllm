"""Abuse / cost protection.

Two independent guards:

1. Per-sender message cap (``select_recent``): bound how many of a sender's buffered
   messages reach the LLM in one dispatch.
2. Global LLM-call cap (``check_global_cap`` / ``record_call``): an absolute ceiling and an
   optional rolling rate window, backed by the persisted ``UsageCounter`` so it survives
   restarts and is shared across worker iterations.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .config import Settings
from .models import UsageCounter, as_naive_utc, utcnow


def select_recent(items: list, max_n: int) -> tuple[list, int]:
    """Keep the most recent ``max_n`` items. Returns (kept, dropped_count)."""
    if max_n <= 0 or len(items) <= max_n:
        return items, 0
    return items[-max_n:], len(items) - max_n


def _get_counter(session: Session, now: dt.datetime) -> UsageCounter:
    counter = session.get(UsageCounter, 1)
    if counter is None:
        counter = UsageCounter(
            id=1, window_start=now, calls_in_window=0, calls_total=0
        )
        session.add(counter)
        session.flush()
    return counter


def _maybe_reset_window(
    counter: UsageCounter, settings: Settings, now: dt.datetime
) -> None:
    if settings.global_window_seconds <= 0:
        return
    window = dt.timedelta(seconds=settings.global_window_seconds)
    if now - as_naive_utc(counter.window_start) >= window:
        counter.window_start = now
        counter.calls_in_window = 0


def check_global_cap(
    session: Session, settings: Settings, now: dt.datetime | None = None
) -> bool:
    """Return True if another LLM call is permitted under the global caps."""
    now = as_naive_utc(now) if now else utcnow()
    counter = _get_counter(session, now)
    _maybe_reset_window(counter, settings, now)

    if settings.global_max_llm_calls_total > 0:
        if counter.calls_total >= settings.global_max_llm_calls_total:
            return False
    if settings.global_max_llm_calls_per_window > 0:
        if counter.calls_in_window >= settings.global_max_llm_calls_per_window:
            return False
    return True


def record_call(
    session: Session, settings: Settings, now: dt.datetime | None = None
) -> None:
    """Record one successful LLM call against the global counters."""
    now = as_naive_utc(now) if now else utcnow()
    counter = _get_counter(session, now)
    _maybe_reset_window(counter, settings, now)
    counter.calls_in_window += 1
    counter.calls_total += 1
