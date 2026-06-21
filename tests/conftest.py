"""Test configuration.

Sets a throwaway SQLite DB and disables Twilio signature validation *before* any smsllm
module is imported (db.py builds its engine at import time from these env vars).
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="smsllm-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["VALIDATE_TWILIO_SIGNATURE"] = "false"
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_token")

import pytest  # noqa: E402

from smsllm.db import engine, init_db  # noqa: E402
from smsllm.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield
    Base.metadata.drop_all(engine)
