from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import CallerContext, FakeWebexPort, InMemoryEvidenceRetriever, Lesson9ApprovalWebexPort, MayaAgent


def test_webex_handoff_is_idempotent_and_not_direct_write() -> None:
    caller = CallerContext("E004", "UG_HR")
    port = FakeWebexPort()
    agent = MayaAgent(InMemoryEvidenceRetriever(), port)
    text = "Understood, I'll route it to Tom. Go ahead and file the Webex access request for her now."

    first = agent.handle_turn_sync("thread-s2", caller, 10, text)
    second = agent.handle_turn_sync("thread-s2", caller, 10, text)

    assert len(port.calls) == 1
    assert first.handoffs[0].request_id == second.handoffs[0].request_id
    assert "create_access_request" not in first.operational_tool_calls
    assert port.calls[0].employee_id == "E001"
    assert port.calls[0].software == "Webex"
    assert port.calls[0].caller_employee_id == "E004"
    assert port.calls[0].idempotency_key == "maya:E001:webex:S2-onboarding-maya"


def test_lesson9_webex_port_creates_pending_access_request() -> None:
    caller = CallerContext("E004", "UG_HR")
    port = Lesson9ApprovalWebexPort()
    agent = MayaAgent(InMemoryEvidenceRetriever(), port)
    text = "Understood, I'll route it to Tom. Go ahead and file the Webex access request for her now."

    first = agent.handle_turn_sync("thread-lesson9-port", caller, 10, text)
    second = agent.handle_turn_sync("thread-lesson9-port", caller, 10, text)

    assert len(port.calls) == 1
    assert first.handoffs[0].request_id.startswith("AR")
    assert first.handoffs[0].status == "pending_approval"
    assert first.handoffs[0].request_id == second.handoffs[0].request_id
