from smsllm.formatting import budget_instruction, enforce


def test_short_text_unchanged():
    assert enforce("hello", 255) == ["hello"]


def test_split_respects_budget_and_breaks_on_whitespace():
    text = " ".join(["word"] * 100)  # 499 chars
    segments = enforce(text, 50, policy="split")
    assert len(segments) > 1
    assert all(len(s) <= 50 for s in segments)
    # No content lost (whitespace boundaries only).
    assert "".join(segments).replace(" ", "") == text.replace(" ", "")


def test_split_hard_cuts_a_long_token():
    text = "x" * 120
    segments = enforce(text, 50, policy="split")
    assert all(len(s) <= 50 for s in segments)
    assert "".join(segments) == text


def test_truncate_clips_with_ellipsis():
    text = "a" * 300
    segments = enforce(text, 100, policy="truncate")
    assert len(segments) == 1
    assert len(segments[0]) <= 100
    assert segments[0].endswith("…")


def test_budget_instruction_mentions_limit():
    assert "255" in budget_instruction(255)
