import datetime as dt

from smsllm.buffer import record_inbound
from smsllm.db import session_scope
from smsllm.models import BotConfig, Conversation


def _make_bot(session, debounce=300):
    bot = BotConfig(
        twilio_number="+15550000001",
        adapter="openai_compat",
        model="m",
        debounce_seconds=debounce,
    )
    session.add(bot)
    session.flush()
    return bot


def test_record_inbound_creates_conversation_and_arms_timer():
    now = dt.datetime(2026, 1, 1)  # naive UTC (storage convention)
    with session_scope() as s:
        bot = _make_bot(s, debounce=300)
        convo = record_inbound(s, bot, "+15551112222", "hi", now=now)
        assert convo.status == "open"
        assert convo.fire_at == now + dt.timedelta(seconds=300)
        assert len(convo.messages) == 1


def test_second_message_extends_timer_and_appends():
    t0 = dt.datetime(2026, 1, 1, 0, 0, 0)  # naive UTC
    t1 = t0 + dt.timedelta(seconds=60)
    with session_scope() as s:
        bot = _make_bot(s, debounce=300)
        record_inbound(s, bot, "+15551112222", "one", now=t0)
        convo = record_inbound(s, bot, "+15551112222", "two", now=t1)

    with session_scope() as s:
        rows = s.query(Conversation).all()
        assert len(rows) == 1  # same open conversation reused
        convo = rows[0]
        assert convo.fire_at == t1 + dt.timedelta(seconds=300)
        assert [m.body for m in convo.messages] == ["one", "two"]
