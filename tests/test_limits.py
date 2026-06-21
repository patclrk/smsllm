import datetime as dt

from smsllm.config import Settings
from smsllm.db import session_scope
from smsllm.limits import check_global_cap, record_call, select_recent


def test_select_recent_keeps_most_recent():
    kept, dropped = select_recent(["a", "b", "c", "d"], 2)
    assert kept == ["c", "d"]
    assert dropped == 2


def test_select_recent_no_cap_or_under_limit():
    assert select_recent(["a", "b"], 0) == (["a", "b"], 0)
    assert select_recent(["a", "b"], 5) == (["a", "b"], 0)


def test_absolute_ceiling_blocks_after_limit():
    settings = Settings(global_max_llm_calls_total=2, global_max_llm_calls_per_window=0)
    with session_scope() as s:
        assert check_global_cap(s, settings)
        record_call(s, settings)
        record_call(s, settings)
        assert not check_global_cap(s, settings)  # 2 reached


def test_record_increments_only_count_and_persists_across_sessions():
    settings = Settings(global_max_llm_calls_total=5)
    with session_scope() as s:
        record_call(s, settings)
        record_call(s, settings)
    # New session = simulates a restart reading the persisted counter.
    with session_scope() as s:
        assert check_global_cap(s, settings)
        from smsllm.models import UsageCounter

        counter = s.get(UsageCounter, 1)
        assert counter.calls_total == 2


def test_window_cap_resets_after_window():
    settings = Settings(
        global_max_llm_calls_total=0,
        global_max_llm_calls_per_window=1,
        global_window_seconds=60,
    )
    t0 = dt.datetime(2026, 1, 1, 0, 0, 0)  # naive UTC
    with session_scope() as s:
        assert check_global_cap(s, settings, now=t0)
        record_call(s, settings, now=t0)
        assert not check_global_cap(s, settings, now=t0)  # window full
        # 61s later -> window rolls over, allowed again.
        later = t0 + dt.timedelta(seconds=61)
        assert check_global_cap(s, settings, now=later)
