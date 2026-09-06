from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from maya import ops
from webex import ApprovalUpdate, WebexAccessWorkflow, WebexCaseInput
from webex_checks import load_cases, roll_up, score_case
from run_webex_disagreement_probe import run as run_disagreement_probe


def test_rachel_webex_reuses_existing_records_and_does_not_grant() -> None:
    ops.reset_conn()
    decision = WebexAccessWorkflow().handle(
        WebexCaseInput(
            request="I joined Customer Success and need Webex access. Webex says my account is not licensed."
        )
    )

    assert decision.employee_id == "E010"
    assert decision.existing_ticket_id == "T001"
    assert decision.existing_request_id == "AR001"
    assert decision.active_seats == 42
    assert decision.seat_limit == 40
    assert decision.status == "blocked_pending_approvals"
    assert decision.granted_access is False
    assert "create_access_request" not in decision.operational_tool_calls
    assert "not granted" in decision.answer


def test_finance_approval_is_persisted_without_granting_access() -> None:
    ops.reset_conn()
    decision = WebexAccessWorkflow().handle(
        WebexCaseInput(
            request="Finance approved AP002 for Rachel's Webex expansion.",
            caller_employee_id="E011",
            approval_updates=(
                ApprovalUpdate(
                    approval_id="AP002",
                    status="approved",
                    actor_employee_id="E011",
                    reason="Finance approved expansion review.",
                ),
            ),
        )
    )

    statuses = {approval["approval_id"]: approval["status"] for approval in decision.approvals}
    assert statuses["AP002"] == "approved"
    assert statuses["AP001"] == "needed"
    assert decision.status == "blocked_pending_approvals"
    assert decision.granted_access is False


def test_webex_eval_cases_score_cleanly() -> None:
    workflow = WebexAccessWorkflow()
    for case in load_cases():
        ops.reset_conn()
        updates = tuple(ApprovalUpdate(**item) for item in case.get("approval_updates", []))
        decision = workflow.handle(
            WebexCaseInput(
                request=case["request"],
                employee_id=case.get("employee_id", "E010"),
                caller_employee_id=case.get("caller_employee_id", "E010"),
                caller_user_group=case.get("caller_user_group", "UG_REGULAR"),
                approval_updates=updates,
            )
        )
        scores = score_case(case, decision.__dict__)
        scores.update(roll_up({name: value for name, (value, _) in scores.items()}))
        assert scores["turn_pass"][0] == 1.0, case["id"]


def test_webex_disagreement_probe_fails_only_brittle_fact_recall() -> None:
    result = run_disagreement_probe(trace=False)

    assert result["scores"]["fact_recall"] == 0.0
    assert result["scores"]["turn_pass"] == 0.0
    assert result["scores"]["no_grant_claim"] == 1.0
    assert result["scores"]["approval_persistence"] == 1.0
