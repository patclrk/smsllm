"""Turn a buffered conversation into one LLM call and an SMS reply.

The conversation is expected to already be claimed (``status == 'processing'``) by the
worker. The DB session is never held across the ``await`` on the LLM, so a slow provider
call doesn't lock the database:

  phase 1 (sync)  : load config + messages, enforce caps, capture a plain plan
  phase 2 (async) : call the LLM provider
  phase 3 (sync)  : record usage, send SMS, persist the reply, close the conversation
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from sqlalchemy import select

from .config import Settings
from .db import session_scope
from .formatting import budget_instruction, enforce
from .limits import check_global_cap, record_call, select_recent
from .llm import ChatMessage, GenParams, LLMError, get_adapter
from .models import BotConfig, Conversation, Message
from .twilio_client import send_sms

logger = logging.getLogger(__name__)


@dataclass
class _Plan:
    sender_number: str
    twilio_number: str
    adapter: str
    params: GenParams
    messages: list[ChatMessage]
    length_budget_chars: int
    overflow_policy: str


def _build_history(session, bot: BotConfig, sender_number: str) -> list[ChatMessage]:
    if not bot.include_history or bot.history_turns <= 0:
        return []
    rows = session.scalars(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.twilio_number == bot.twilio_number,
            Conversation.sender_number == sender_number,
            Conversation.status == "done",
        )
        .order_by(Message.created_at.desc())
        .limit(bot.history_turns)
    ).all()
    rows.reverse()
    return [
        ChatMessage(role="assistant" if m.direction == "out" else "user", content=m.body)
        for m in rows
    ]


async def dispatch_conversation(convo_id: int, settings: Settings) -> None:
    # --- phase 1: load, check caps, build the plan (sync) ---
    plan: _Plan | None = None
    unavailable: tuple[str, str, str] | None = None  # (to, from, body)

    with session_scope() as session:
        convo = session.get(Conversation, convo_id)
        if convo is None:
            return
        bot = session.scalars(
            select(BotConfig).where(BotConfig.twilio_number == convo.twilio_number)
        ).first()
        if bot is None or not bot.enabled:
            convo.status = "done"
            return

        if not check_global_cap(session, settings):
            convo.status = "skipped"
            logger.warning("global LLM-call cap reached; skipping convo %s", convo_id)
            if bot.unavailable_message:
                unavailable = (convo.sender_number, bot.twilio_number, bot.unavailable_message)
        else:
            inbound = [m.body for m in convo.messages if m.direction == "in"]
            kept, dropped = select_recent(inbound, bot.max_messages_per_sender)
            if dropped:
                logger.info(
                    "per-sender cap dropped %s message(s) for %s",
                    dropped,
                    convo.sender_number,
                )
            history = _build_history(session, bot, convo.sender_number)
            current = [ChatMessage(role="user", content=b) for b in kept]
            system_prompt = "\n\n".join(
                p for p in (bot.system_prompt, budget_instruction(bot.length_budget_chars)) if p
            )
            api_key = os.environ.get(bot.api_key_ref, "")
            plan = _Plan(
                sender_number=convo.sender_number,
                twilio_number=bot.twilio_number,
                adapter=bot.adapter,
                params=GenParams(
                    model=bot.model,
                    api_key=api_key,
                    base_url=bot.base_url,
                    system_prompt=system_prompt,
                ),
                messages=history + current,
                length_budget_chars=bot.length_budget_chars,
                overflow_policy=bot.overflow_policy,
            )

    if unavailable is not None:
        await asyncio.to_thread(send_sms, settings, unavailable[0], unavailable[1], [unavailable[2]])
        return
    if plan is None:
        return

    # --- phase 2: call the LLM (async, no DB session held) ---
    try:
        adapter = get_adapter(plan.adapter)
        reply = await adapter.generate(plan.messages, plan.params)
    except (LLMError, ValueError) as exc:
        logger.error("dispatch convo %s failed: %s", convo_id, exc)
        with session_scope() as session:
            convo = session.get(Conversation, convo_id)
            if convo is not None:
                convo.status = "error"
        return

    # --- phase 3: record usage, send, persist (sync) ---
    with session_scope() as session:
        record_call(session, settings)

    segments = enforce(reply, plan.length_budget_chars, plan.overflow_policy)
    sids = await asyncio.to_thread(
        send_sms, settings, plan.sender_number, plan.twilio_number, segments
    )

    with session_scope() as session:
        convo = session.get(Conversation, convo_id)
        if convo is not None:
            for i, segment in enumerate(segments):
                if not segment:
                    continue
                convo.messages.append(
                    Message(
                        direction="out",
                        body=segment,
                        twilio_sid=sids[i] if i < len(sids) else "",
                    )
                )
            convo.status = "done"
