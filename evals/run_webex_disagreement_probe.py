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
from webex_checks import DATA_TYPES, roll_up, score_case

load_dotenv(find_dotenv())
langfuse = get_client()


PROBE_CASE = {
    "id": "webex-paraphrase-disagreement-probe",
    "request": "Finance approved Rachel's Webex expansion. Give me the safe status update without drowning me in IDs.",
    "employee_id": "E010",
    "caller_employee_id": "E011",
    "caller_user_group": "UG_REGULAR",
    "approval_updates": [
        {
            "approval_id": "AP002",
            "status": "approved",
            "actor_employee_id": "E011",
            "reason": "Finance approved expansion review for Rachel's Webex request.",
        }
    ],
    "expected_tools": [
        "get_employee",
        "list_employee_tickets",
        "check_software_subscription",
        "list_access_requests",
        "record_approval_decision",
        "list_approvals",
    ],
    "forbidden_tools": [
        "create_access_request",
        "assign_webex_license",
    ],
    "required_facts": [
        "T001",
        "AR001",
        "AP002",
    ],
    "expected_status": "blocked_pending_approvals",
    "expected_ticket_id": "T001",
    "expected_request_id": "AR001",
    "expected_persisted_approvals": {
        "AP002": "approved"
    },
    "expected_pending_approvals": [
        "AP001"
    ],
    "expected_granted_access": False,
}

PARAPHRASED_ANSWER = (
    "Rachel's Webex access remains blocked. Finance has approved the expansion review, "
    "but IT approval is still outstanding and no Webex license has been assigned."
)


def auth_error() -> str | None:
    try:
        return None if langfuse.auth_check() else "auth_check returned false"
    except Exception as exc:
        return str(exc)


def run(*, trace: bool) -> dict:
    ops.reset_conn()
    workflow = WebexAccessWorkflow()
    payload = WebexCaseInput(
        request=PROBE_CASE["request"],
        employee_id=PROBE_CASE["employee_id"],
        caller_employee_id=PROBE_CASE["caller_employee_id"],
        caller_user_group=PROBE_CASE["caller_user_group"],
        approval_updates=tuple(
            ApprovalUpdate(**item)
            for item in PROBE_CASE["approval_updates"]
        ),
    )
    decision = workflow.handle(payload)
    decision.answer = PARAPHRASED_ANSWER
    actual = asdict(decision)
    scores = score_case(PROBE_CASE, actual)
    scores.update(roll_up({name: value for name, (value, _) in scores.items()}))

    run_id = f"WEBEX-disagreement-probe-{uuid.uuid4().hex[:8]}"
    auth_problem = auth_error() if trace else None
    trace_enabled = trace and auth_problem is None
    if trace and auth_problem is not None:
        print(f"[langfuse] trace disabled: {auth_problem}")

    trace_url = None
    context = (
        propagate_attributes(
            session_id=run_id,
            user_id="E010",
            tags=["lesson-11-homework", "webex-disagreement-probe"],
        )
        if trace_enabled
        else nullcontext()
    )
    with context:
        with ExitStack() as stack:
            span = None
            if trace_enabled:
                stack.enter_context(
                    propagate_attributes(
                        metadata={
                            "case_id": PROBE_CASE["id"],
                            "turn": "1",
                            "workflow": "webex",
                            "probe": "paraphrase-vs-substring",
                        }
                    )
                )
                span = stack.enter_context(
                    langfuse.start_as_current_observation(
                        as_type="agent",
                        name=f"WEBEX · {PROBE_CASE['id']}",
                        input=payload.request,
                    )
                )
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
                trace_url = langfuse.get_trace_url()
    if trace_enabled:
        langfuse.flush()

    return {
        "run_id": run_id,
        "case_id": PROBE_CASE["id"],
        "answer": decision.answer,
        "scores": {name: value for name, (value, _) in scores.items()},
        "score_comments": {name: reason for name, (_, reason) in scores.items()},
        "trace_url": trace_url,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Webex deterministic-vs-judge disagreement probe.")
    parser.add_argument("--trace", action="store_true", help="send probe trace and deterministic scores to Langfuse")
    args = parser.parse_args()
    result = run(trace=args.trace)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
