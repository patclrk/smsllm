"""ORM models.

- ``BotConfig``   — routing table: one row per Twilio number -> its own LLM config.
- ``Conversation`` — per-(bot, sender) debounce buffer with a persisted ``fire_at`` timer.
- ``Message``     — inbound/outbound messages; doubles as history when enabled.
- ``UsageCounter`` — single row tracking global LLM-call counts for the operator cap.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    """Naive UTC. SQLite does not preserve tzinfo, so we keep everything naive-UTC to
    avoid mixing aware/naive datetimes across DB roundtrips and SQL comparisons."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def as_naive_utc(value: dt.datetime) -> dt.datetime:
    """Normalize any datetime to naive UTC."""
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


class Base(DeclarativeBase):
    pass


class BotConfig(Base):
    __tablename__ = "bot_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    twilio_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")

    # 'openai_compat' (default, covers most providers) | 'anthropic' | 'gemini'
    adapter: Mapped[str] = mapped_column(String(32), default="openai_compat")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    # Name of the env var holding the API key (never the raw key).
    api_key_ref: Mapped[str] = mapped_column(String(128), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")

    length_budget_chars: Mapped[int] = mapped_column(Integer, default=255)
    # 'split' into multiple SMS or 'truncate' when the reply exceeds the budget.
    overflow_policy: Mapped[str] = mapped_column(String(16), default="split")
    debounce_seconds: Mapped[int] = mapped_column(Integer, default=300)
    include_history: Mapped[bool] = mapped_column(Boolean, default=False)
    history_turns: Mapped[int] = mapped_column(Integer, default=10)

    # Per-sender cap: at most this many of a sender's buffered messages are forwarded to
    # the LLM in a single dispatch (most recent kept).
    max_messages_per_sender: Mapped[int] = mapped_column(Integer, default=10)
    # Optional message sent when the global cap is exhausted (empty = stay silent).
    unavailable_message: Mapped[str] = mapped_column(Text, default="")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversation"
    __table_args__ = (
        UniqueConstraint(
            "twilio_number", "sender_number", "status", name="uq_open_conversation"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    twilio_number: Mapped[str] = mapped_column(String(32), index=True)
    sender_number: Mapped[str] = mapped_column(String(32), index=True)
    # 'open' (buffering) | 'processing' (claimed by a worker) | 'done' | 'skipped'
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    fire_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversation.id"), index=True
    )
    direction: Mapped[str] = mapped_column(String(3))  # 'in' | 'out'
    body: Mapped[str] = mapped_column(Text)
    twilio_sid: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class UsageCounter(Base):
    """Single-row counter (id == 1) for the global LLM-call cap."""

    __tablename__ = "usage_counter"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    window_start: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    calls_in_window: Mapped[int] = mapped_column(Integer, default=0)
    calls_total: Mapped[int] = mapped_column(Integer, default=0)
