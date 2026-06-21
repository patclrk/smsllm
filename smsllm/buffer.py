"""Per-(number, sender) message buffering with a persisted debounce timer."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BotConfig, Conversation, Message, as_naive_utc, utcnow


def record_inbound(
    session: Session,
    bot: BotConfig,
    sender_number: str,
    body: str,
    twilio_sid: str = "",
    now: dt.datetime | None = None,
) -> Conversation:
    """Append an inbound message to the sender's open conversation (creating it if
    needed) and (re)arm the debounce timer to ``now + bot.debounce_seconds``."""
    now = as_naive_utc(now) if now else utcnow()
    convo = session.scalars(
        select(Conversation).where(
            Conversation.twilio_number == bot.twilio_number,
            Conversation.sender_number == sender_number,
            Conversation.status == "open",
        )
    ).first()

    if convo is None:
        convo = Conversation(
            twilio_number=bot.twilio_number,
            sender_number=sender_number,
            status="open",
            fire_at=now + dt.timedelta(seconds=bot.debounce_seconds),
        )
        session.add(convo)
        session.flush()
    else:
        convo.fire_at = now + dt.timedelta(seconds=bot.debounce_seconds)

    convo.messages.append(
        Message(direction="in", body=body, twilio_sid=twilio_sid)
    )
    return convo
