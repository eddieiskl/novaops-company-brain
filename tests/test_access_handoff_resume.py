from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import ops
from webex.write_gate import RecordedApprovalWriteGate


def test_new_access_request_pauses_survives_restart_and_resumes_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NOVAOPS_DB_PATH", str(tmp_path / "approval-resume.sqlite3"))
    ops.reset_conn()
    handoff = ops.prepare_access_handoff(
        conversation_id="S2-onboarding-maya",
        subject_employee_id="E001",
        software="Webex",
        business_justification="Maya needs Webex for Customer Success calls.",
        caller_employee_id="E004",
        idempotency_key="S2:E001:Webex",
    )

    assert handoff["status"] == "pending_approval"
    assert ops.list_access_requests("E001", "Webex") == []
    blocked, request = RecordedApprovalWriteGate().resume_access_handoff(handoff["handoff_id"])
    assert blocked.released is False
    assert request is None

    approval = ops.list_approvals(handoff["handoff_id"])[0]
    assert approval["approver_id"] == "E018"
    ops.reset_conn(reseed=False)
    ops.record_approval_decision(approval["approval_id"], "approved", "E018", "Approved for Maya's role.")

    gate = RecordedApprovalWriteGate()
    released, first = gate.resume_access_handoff(handoff["handoff_id"])
    replayed, second = gate.resume_access_handoff(handoff["handoff_id"])

    assert released.released is True
    assert replayed.released is True
    assert first["request_id"] == second["request_id"]
    assert first["status"] == "blocked"
    assert len(ops.list_access_requests("E001", "Webex")) == 1
    assert ops.get_access_handoff(handoff["handoff_id"])["status"] == "released"


def test_preparing_same_handoff_twice_is_idempotent() -> None:
    ops.reset_conn()
    kwargs = {
        "conversation_id": "thread-123",
        "subject_employee_id": "E001",
        "software": "Webex",
        "business_justification": "Customer calls.",
        "caller_employee_id": "E004",
        "idempotency_key": "thread-123:E001:Webex",
    }

    first = ops.prepare_access_handoff(**kwargs)
    second = ops.prepare_access_handoff(**kwargs)

    assert first["handoff_id"] == second["handoff_id"]
    assert len(ops.list_approvals(first["handoff_id"])) == 1
