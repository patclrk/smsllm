"""End-to-end worker -> dispatch flow with the LLM and Twilio send mocked."""

import datetime as dt

import pytest

import smsllm.dispatch as dispatch_mod
from smsllm.config import Settings
from smsllm.db import session_scope
from smsllm.models import BotConfig, Conversation, Message, UsageCounter, utcnow
from smsllm.worker import process_due_once


class _FakeAdapter:
    def __init__(self, reply):
        self.reply = reply
        self.received = None

    async def generate(self, messages, params):
        self.received = messages
        return self.reply


@pytest.fixture
def captured_sends(monkeypatch):
    sends = []

    def fake_send(settings, to, from_, segments):
        sends.append({"to": to, "from": from_, "segments": segments})
        return [f"SM{i}" for i, _ in enumerate(segments)]

    monkeypatch.setattr(dispatch_mod, "send_sms", fake_send)
    return sends


def _seed_due_conversation(bodies, *, max_per_sender=10, budget=255):
    with session_scope() as s:
        s.add(
            BotConfig(
                twilio_number="+15550000001",
                adapter="openai_compat",
                model="m",
                length_budget_chars=budget,
                max_messages_per_sender=max_per_sender,
                api_key_ref="TEST_KEY",
            )
        )
        convo = Conversation(
            twilio_number="+15550000001",
            sender_number="+15551112222",
            status="open",
            fire_at=utcnow() - dt.timedelta(seconds=1),  # already due
        )
        for b in bodies:
            convo.messages.append(Message(direction="in", body=b))
        s.add(convo)


async def test_due_conversation_dispatches_and_replies(monkeypatch, captured_sends):
    monkeypatch.setenv("TEST_KEY", "secret")
    fake = _FakeAdapter("hello back")
    monkeypatch.setattr(dispatch_mod, "get_adapter", lambda name: fake)

    _seed_due_conversation(["hi", "there"])
    dispatched = await process_due_once(Settings())
    assert dispatched == 1

    assert len(captured_sends) == 1
    assert captured_sends[0]["to"] == "+15551112222"
    assert captured_sends[0]["segments"] == ["hello back"]

    with session_scope() as s:
        convo = s.query(Conversation).one()
        assert convo.status == "done"
        outbound = [m.body for m in convo.messages if m.direction == "out"]
        assert outbound == ["hello back"]
        assert s.get(UsageCounter, 1).calls_total == 1


async def test_per_sender_cap_limits_messages_sent_to_llm(monkeypatch, captured_sends):
    monkeypatch.setenv("TEST_KEY", "secret")
    fake = _FakeAdapter("ok")
    monkeypatch.setattr(dispatch_mod, "get_adapter", lambda name: fake)

    _seed_due_conversation(["m1", "m2", "m3", "m4", "m5"], max_per_sender=2)
    await process_due_once(Settings())

    # Only the 2 most recent inbound messages reach the LLM.
    assert [m.content for m in fake.received] == ["m4", "m5"]


async def test_global_cap_skips_dispatch(monkeypatch, captured_sends):
    monkeypatch.setenv("TEST_KEY", "secret")
    fake = _FakeAdapter("should not be called")
    monkeypatch.setattr(dispatch_mod, "get_adapter", lambda name: fake)

    _seed_due_conversation(["hi"])
    settings = Settings(global_max_llm_calls_total=1, global_max_llm_calls_per_window=0)
    # Pre-exhaust the absolute ceiling.
    with session_scope() as s:
        s.add(UsageCounter(id=1, window_start=utcnow(), calls_in_window=1, calls_total=1))

    await process_due_once(settings)

    assert captured_sends == []  # no unavailable_message configured -> silent
    assert fake.received is None
    with session_scope() as s:
        assert s.query(Conversation).one().status == "skipped"
