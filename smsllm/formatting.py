"""Reply length-budget enforcement.

The prompt asks the LLM to stay under the budget (primary control); this is the hard
safety net. ``split`` breaks an over-budget reply into ordered SMS-sized chunks on
whitespace boundaries; ``truncate`` returns a single clipped chunk.
"""

from __future__ import annotations

ELLIPSIS = "…"


def budget_instruction(length_budget_chars: int) -> str:
    return (
        f"Reply in plain text only (no markdown) and keep it under "
        f"{length_budget_chars} characters."
    )


def enforce(text: str, length_budget_chars: int, policy: str = "split") -> list[str]:
    """Return the SMS segments to send (always at least one).

    ``split``    -> one or more chunks, each <= budget.
    ``truncate`` -> a single chunk <= budget, clipped with an ellipsis if needed.
    """
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= length_budget_chars:
        return [text]
    if policy == "truncate":
        return [_truncate(text, length_budget_chars)]
    return _split(text, length_budget_chars)


def _truncate(text: str, limit: int) -> str:
    if limit <= 1:
        return text[:limit]
    clipped = text[: limit - 1].rstrip()
    return clipped + ELLIPSIS


def _split(text: str, limit: int) -> list[str]:
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        # Prefer to break on the last whitespace within the window.
        cut = window.rfind(" ")
        if cut <= 0:
            cut = limit  # no space: hard cut a long token
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
