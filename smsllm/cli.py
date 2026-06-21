"""Command-line admin: initialize the DB, register bots, run the server."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from .config import get_settings
from .db import init_db, session_scope
from .llm.registry import available_adapters
from .models import BotConfig


def _cmd_initdb(_args: argparse.Namespace) -> None:
    init_db()
    print("database initialized")


def _cmd_add_bot(args: argparse.Namespace) -> None:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        existing = session.scalars(
            select(BotConfig).where(BotConfig.twilio_number == args.number)
        ).first()
        if existing is not None:
            raise SystemExit(f"a bot already exists for {args.number}")
        bot = BotConfig(
            twilio_number=args.number,
            name=args.name or "",
            adapter=args.adapter,
            base_url=args.base_url or "",
            model=args.model or "",
            api_key_ref=args.api_key_ref or "",
            system_prompt=args.system_prompt or "",
            length_budget_chars=args.length_budget or settings.default_length_budget_chars,
            overflow_policy=args.overflow_policy,
            debounce_seconds=args.debounce_seconds or settings.default_debounce_seconds,
            include_history=args.include_history,
            history_turns=args.history_turns,
            max_messages_per_sender=(
                args.max_messages_per_sender or settings.default_max_messages_per_sender
            ),
            unavailable_message=args.unavailable_message or "",
        )
        session.add(bot)
    print(f"added bot for {args.number} (adapter={args.adapter}, model={args.model})")


def _cmd_list_bots(_args: argparse.Namespace) -> None:
    init_db()
    with session_scope() as session:
        bots = session.scalars(select(BotConfig).order_by(BotConfig.twilio_number)).all()
        if not bots:
            print("(no bots configured)")
            return
        for b in bots:
            state = "enabled" if b.enabled else "disabled"
            print(
                f"{b.twilio_number}  [{state}]  adapter={b.adapter}  model={b.model}  "
                f"debounce={b.debounce_seconds}s  budget={b.length_budget_chars}  "
                f"max_msgs/sender={b.max_messages_per_sender}"
            )


def _cmd_run(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("smsllm.main:app", host=args.host, port=args.port, reload=args.reload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smsllm")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("initdb", help="create database tables").set_defaults(func=_cmd_initdb)

    p_add = sub.add_parser("add-bot", help="register a Twilio number -> LLM config")
    p_add.add_argument("--number", required=True, help="Twilio number, e.g. +15555550123")
    p_add.add_argument("--name", default="")
    p_add.add_argument(
        "--adapter", default="openai_compat", choices=available_adapters()
    )
    p_add.add_argument("--base-url", default="")
    p_add.add_argument("--model", default="")
    p_add.add_argument("--api-key-ref", default="", help="env var NAME holding the key")
    p_add.add_argument("--system-prompt", default="")
    p_add.add_argument("--length-budget", type=int, default=0)
    p_add.add_argument(
        "--overflow-policy", default="split", choices=["split", "truncate"]
    )
    p_add.add_argument("--debounce-seconds", type=int, default=0)
    p_add.add_argument("--include-history", action="store_true")
    p_add.add_argument("--history-turns", type=int, default=10)
    p_add.add_argument("--max-messages-per-sender", type=int, default=0)
    p_add.add_argument("--unavailable-message", default="")
    p_add.set_defaults(func=_cmd_add_bot)

    sub.add_parser("list-bots", help="list configured bots").set_defaults(
        func=_cmd_list_bots
    )

    p_run = sub.add_parser("run", help="run the FastAPI server + worker")
    p_run.add_argument("--host", default="0.0.0.0")
    p_run.add_argument("--port", type=int, default=8000)
    p_run.add_argument("--reload", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
