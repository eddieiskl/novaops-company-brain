from __future__ import annotations

import argparse
import json
import sys
import uuid
from contextlib import ExitStack, nullcontext
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import find_dotenv, load_dotenv

from langfuse import get_client, propagate_attributes

from maya import ops
from webex import ApprovalUpdate, WebexAccessWorkflow, WebexCaseInput
from webex_checks import DATA_TYPES, load_cases, roll_up, score_case

load_dotenv(find_dotenv())
langfuse = get_client()


def auth_error() -> str | None:
    try:
        return None if langfuse.auth_check() else "auth_check returned false"
    except Exception as exc:
        return str(exc)


def case_input(case: dict) -> WebexCaseInput:
    updates = tuple(ApprovalUpdate(**item) for item in case.get("approval_updates", []))
    return WebexCaseInput(
        request=case["request"],
        employee_id=case.get("employee_id", "E010"),
        software=case.get("software", "Webex"),
        caller_employee_id=case.get("caller_employee_id", case.get("employee_id", "E010")),
        caller_user_group=case.get("caller_user_group", "UG_REGULAR"),
        approval_updates=updates,
    )


def run(*, trace: bool) -> tuple[list[dict], list[str], str]:
    cases = load_cases()
    workflow = WebexAccessWorkflow()
    run_id = f"WEBEX-rachel-baseline-{uuid.uuid4().hex[:8]}"
    rows: list[dict] = []
    errors: list[str] = []

    auth_problem = auth_error() if trace else None
    trace_enabled = trace and auth_problem is None
    if trace and auth_problem is not None:
        print(f"[langfuse] trace disabled: {auth_problem}")
    trace_context = (
        propagate_attributes(
            session_id=run_id,
            user_id="E010",
            tags=["lesson-11-homework", "webex-baseline"],
        )
        if trace_enabled
        else nullcontext()
    )
    with trace_context:
        for index, case in enumerate(cases, start=1):
            ops.reset_conn()
            payload = case_input(case)
            with ExitStack() as stack:
                span = None
                if trace_enabled:
                    stack.enter_context(
                        propagate_attributes(
                            metadata={"case_id": case["id"], "turn": str(index), "workflow": "webex"}
                        )
                    )
                    span = stack.enter_context(
                        langfuse.start_as_current_observation(
                            as_type="agent",
                            name=f"WEBEX · {case['id']}",
                            input=payload.request,
                        )
                    )
                decision = workflow.handle(payload)
                actual = asdict(decision)
                scores = score_case(case, actual)
                scores.update(roll_up({name: value for name, (value, _) in scores.items()}))

                if span is not None:
                    span.update(
                        output=decision.answer,
                        metadata={"webex_decision": decision.trace_projection()},
                    )
                    for name, (value, reason) in scores.items():
                        langfuse.score_current_trace(
                            name=f"webex_{name}",
                            value=value,
                            data_type=DATA_TYPES[name],
                            comment=reason,
                        )
                rows.append(
                    {
                        "case_id": case["id"],
                        "status": decision.status,
                        "answer": decision.answer,
                        "scores": {name: value for name, (value, _) in scores.items()},
                        "calls": decision.operational_tool_calls,
                        "trace_url": langfuse.get_trace_url() if span is not None else None,
                    }
                )
                failed = [name for name, (value, _) in scores.items() if value < 1.0]
                if failed:
                    errors.append(f"{case['id']}: failed {', '.join(failed)}")

    if trace_enabled:
        langfuse.flush()
    return rows, errors, run_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Rachel Webex baseline.")
    parser.add_argument("--trace", action="store_true", help="send traces and scores to Langfuse")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args()

    rows, errors, run_id = run(trace=args.trace)
    if args.json:
        print(json.dumps({"run_id": run_id, "rows": rows, "errors": errors}, indent=2))
    else:
        print(f"run_id={run_id}")
        print("case status turn_pass turn_score trace")
        for row in rows:
            print(
                row["case_id"],
                row["status"],
                row["scores"].get("turn_pass"),
                round(row["scores"].get("turn_score", 0.0), 4),
                row["trace_url"] or "-",
            )
    if errors:
        print("\nFAILURES:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\nWebex baseline passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
