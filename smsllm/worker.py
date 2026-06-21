"""Background worker: find conversations whose debounce timer has fired, claim each
atomically, and dispatch it."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import select, update

from .config import Settings
from .db import session_scope
from .dispatch import dispatch_conversation
from .models import Conversation, as_naive_utc, utcnow

logger = logging.getLogger(__name__)


def _find_due_ids(session, now: dt.datetime) -> list[int]:
    return list(
        session.scalars(
            select(Conversation.id)
            .where(Conversation.status == "open", Conversation.fire_at <= now)
            .order_by(Conversation.fire_at)
        )
    )


def _claim(session, convo_id: int) -> bool:
    """Atomically move open -> processing. Returns True if this caller won the claim."""
    result = session.execute(
        update(Conversation)
        .where(Conversation.id == convo_id, Conversation.status == "open")
        .values(status="processing")
    )
    return result.rowcount == 1


async def process_due_once(settings: Settings, now: dt.datetime | None = None) -> int:
    """Claim and dispatch all currently-due conversations. Returns the count dispatched."""
    now = as_naive_utc(now) if now else utcnow()
    with session_scope() as session:
        due_ids = _find_due_ids(session, now)

    dispatched = 0
    for convo_id in due_ids:
        with session_scope() as session:
            claimed = _claim(session, convo_id)
        if not claimed:
            continue
        try:
            await dispatch_conversation(convo_id, settings)
            dispatched += 1
        except Exception:  # never let one bad conversation kill the worker
            logger.exception("unhandled error dispatching convo %s", convo_id)
    return dispatched


async def run_worker(settings: Settings, stop_event: asyncio.Event) -> None:
    logger.info("worker started (poll every %.1fs)", settings.worker_poll_seconds)
    while not stop_event.is_set():
        try:
            await process_due_once(settings)
        except Exception:
            logger.exception("worker iteration failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.worker_poll_seconds
            )
        except asyncio.TimeoutError:
            pass
    logger.info("worker stopped")
