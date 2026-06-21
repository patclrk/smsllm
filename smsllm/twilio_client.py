"""Twilio helpers: inbound signature validation and outbound SMS."""

from __future__ import annotations

from twilio.request_validator import RequestValidator
from twilio.rest import Client

from .config import Settings


def validate_signature(
    settings: Settings, url: str, params: dict[str, str], signature: str
) -> bool:
    """Verify the ``X-Twilio-Signature`` header for an inbound webhook.

    ``url`` must be the exact public URL Twilio posted to and ``params`` the POST form
    fields. Validation is skipped when ``validate_twilio_signature`` is off (local dev).
    """
    if not settings.validate_twilio_signature:
        return True
    if not settings.twilio_auth_token:
        return False
    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(url, params, signature or "")


def _client(settings: Settings) -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_sms(settings: Settings, to: str, from_: str, segments: list[str]) -> list[str]:
    """Send each segment as its own SMS. Returns the created message SIDs."""
    client = _client(settings)
    sids: list[str] = []
    for segment in segments:
        if not segment:
            continue
        msg = client.messages.create(to=to, from_=from_, body=segment)
        sids.append(msg.sid)
    return sids
