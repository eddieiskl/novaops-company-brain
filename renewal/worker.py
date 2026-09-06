from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import time

from maya import ops

from .runtime import build_renewal_workflow_from_env
from .schemas import InternalApprovalEvent


def _print(value) -> None:
    print(json.dumps(asdict(value), indent=2, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="NovaOps offline renewal worker")
    commands = parser.add_subparsers(dest="command", required=True)
    schedule = commands.add_parser("schedule")
    schedule.add_argument("--as-of", default=os.getenv("NOVAOPS_AS_OF", "2026-07-01"))
    approval = commands.add_parser("approval-event")
    approval.add_argument("event_file", type=Path)
    provider = commands.add_parser("provider-reply")
    provider.add_argument("run_id")
    provider.add_argument("fixture_id")
    provider.add_argument("reply_file", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--interval", type=int, default=300)
    commands.add_parser("health")
    args = parser.parse_args()

    if args.command == "health":
        ops.conn().execute("SELECT 1").fetchone()
        print("ok")
        return 0
    if args.command == "schedule":
        _print(build_renewal_workflow_from_env().start(args.as_of))
        return 0
    if args.command == "approval-event":
        event = InternalApprovalEvent(**json.loads(args.event_file.read_text(encoding="utf-8")))
        _print(build_renewal_workflow_from_env().handle_internal_event(event))
        return 0
    if args.command == "provider-reply":
        reply = args.reply_file.read_text(encoding="utf-8")
        _print(build_renewal_workflow_from_env(replies={args.fixture_id: reply}).handle_provider_reply(
            args.run_id, args.fixture_id, reply
        ))
        return 0

    as_of = os.getenv("NOVAOPS_AS_OF", "2026-07-01")
    while True:
        build_renewal_workflow_from_env().start(as_of)
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
