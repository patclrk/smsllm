from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from smsllm.config import Settings
from smsllm.db import session_scope
from smsllm.main import app
from smsllm.models import BotConfig, Conversation
from smsllm.twilio_client import validate_signature

BOT_NUMBER = "+15550000123"
SENDER = "+15557654321"


def _seed_bot():
    with session_scope() as s:
        s.add(BotConfig(twilio_number=BOT_NUMBER, adapter="openai_compat", model="m"))


def test_inbound_creates_conversation_and_buffers_message():
    _seed_bot()
    with TestClient(app) as client:
        resp = client.post(
            "/sms",
            data={"To": BOT_NUMBER, "From": SENDER, "Body": "hello", "MessageSid": "SM1"},
        )
    assert resp.status_code == 200
    assert "<Response>" in resp.text

    with session_scope() as s:
        convos = s.query(Conversation).all()
        assert len(convos) == 1
        assert convos[0].sender_number == SENDER
        assert [m.body for m in convos[0].messages] == ["hello"]


def test_inbound_for_unknown_number_is_ignored():
    with TestClient(app) as client:
        resp = client.post(
            "/sms",
            data={"To": "+19999999999", "From": SENDER, "Body": "hi", "MessageSid": "SM2"},
        )
    assert resp.status_code == 200
    with session_scope() as s:
        assert s.query(Conversation).count() == 0


def test_signature_validation_accepts_valid_rejects_invalid():
    settings = Settings(validate_twilio_signature=True, twilio_auth_token="secret")
    url = "https://example.test/sms"
    params = {"To": BOT_NUMBER, "From": SENDER, "Body": "hello"}
    valid = RequestValidator("secret").compute_signature(url, params)

    assert validate_signature(settings, url, params, valid)
    assert not validate_signature(settings, url, params, "bogus")
