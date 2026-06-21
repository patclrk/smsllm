"""FastAPI app: the Twilio inbound webhook plus the background debounce worker."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy import select

from .buffer import record_inbound
from .config import get_settings
from .db import init_db, session_scope
from .models import BotConfig
from .twilio_client import validate_signature
from .worker import run_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    stop_event = asyncio.Event()
    task = asyncio.create_task(run_worker(settings, stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await task


app = FastAPI(title="smsllm", lifespan=lifespan)


def _twiml() -> Response:
    return Response(content=EMPTY_TWIML, media_type="application/xml")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/sms")
async def inbound_sms(request: Request) -> Response:
    settings = get_settings()
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    signature = request.headers.get("X-Twilio-Signature", "")
    url = settings.public_base_url.rstrip("/") + "/sms"
    if not validate_signature(settings, url, params, signature):
        logger.warning("rejected inbound SMS: bad Twilio signature")
        return Response(status_code=403, content="invalid signature")

    to = params.get("To", "")
    sender = params.get("From", "")
    body = params.get("Body", "")
    sid = params.get("MessageSid", "")
    if not to or not sender:
        return _twiml()

    with session_scope() as session:
        bot = session.scalars(
            select(BotConfig).where(BotConfig.twilio_number == to)
        ).first()
        if bot is None or not bot.enabled:
            logger.info("no enabled bot for %s; ignoring", to)
            return _twiml()
        record_inbound(session, bot, sender, body, sid)

    # Reply is sent asynchronously by the worker after the debounce window.
    return _twiml()
