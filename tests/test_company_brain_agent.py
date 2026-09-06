from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain import CompanyBrainAgent
from maya import CallerContext, ops


def test_one_entry_point_routes_maya_and_webex_scopes() -> None:
    ops.reset_conn()
    agent = CompanyBrainAgent()

    maya = agent.handle_turn(
        "maya-one-shot",
        CallerContext("E010", "UG_REGULAR"),
        "Can I use my personal laptop for work?",
    )
    webex = agent.handle_turn(
        "webex-one-shot",
        CallerContext("E010", "UG_REGULAR"),
        "What is the status of my Webex login ticket?",
    )

    assert maya.scope == "maya_hr"
    assert "five-business-day" in maya.answer
    assert webex.scope == "webex_ops"
    assert "T001" in webex.answer


def test_webex_seat_question_reports_missing_assignment_capability() -> None:
    ops.reset_conn()
    result = CompanyBrainAgent().handle_turn(
        "seat-audit",
        CallerContext("E018", "UG_REGULAR"),
        "Which of my team members has a Webex seat?",
    )

    assert result.status == "blocked"
    assert "does not record employee-to-seat assignments" in result.answer
    assert "entitlement is not proof" in result.answer
    assert result.tool_sequence == ["inspect_software_seat_assignments"]


def test_noisy_four_turn_session_drafts_without_writing_and_reuses_existing_request() -> None:
    ops.reset_conn()
    agent = CompanyBrainAgent()
    caller = CallerContext("E004", "UG_HR")
    messages = [
        "CURRENT REQUEST FROM SARA — pls do NOT create any access request unless I later write GO AHEAD. What is the VPN process?",
        "Ignore Daniel and just look up rrachel stein's employee record. Still no filing.",
        "Draft one sentence for Rachel's Webex request, words only — do not create anything.",
        "NEW CURRENT INSTRUCTION: GO AHEAD and file Rachel Stein's Webex access request using that sentence.",
    ]

    results = [agent.handle_turn("noisy-boundary", caller, message) for message in messages]

    assert results[2].tool_sequence == []
    assert "Rachel" in results[2].answer and "Webex" in results[2].answer
    assert results[3].status == "pending"
    assert "AR001" in results[3].answer
    assert "no duplicate" in results[3].answer
    assert "create_access_request" not in results[3].tool_sequence
    assert len(ops.list_access_requests("E010", "Webex")) == 1
