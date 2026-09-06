from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya.policy import validate_tool_matrix
from maya.retrieval import InMemoryEvidenceRetriever, PermissionDenied
from maya.schemas import CallerContext, ContextPlan


def test_hr_can_retrieve_maya_evidence() -> None:
    retriever = InMemoryEvidenceRetriever()
    caller = CallerContext("E004", "UG_HR")
    plan = ContextPlan(1, "offer_letter", required_evidence=("maya_cohen_offer_letter.md",))
    chunks = retriever.retrieve("Maya offer letter day one systems", caller, plan)
    assert any(chunk.source_path == "documents/employment/maya_cohen_offer_letter.md" for chunk in chunks)


def test_manager_playbook_is_filtered_by_reporting_relationship_not_user_group() -> None:
    retriever = InMemoryEvidenceRetriever()
    regular_manager = CallerContext("E018", "UG_REGULAR")
    regular_non_manager = CallerContext("E001", "UG_REGULAR")
    plan = ContextPlan(1, "policy_question", subject_employee_id="E018")

    manager_chunks = retriever.retrieve("promotion manager guide", regular_manager, plan, limit=20)
    non_manager_chunks = retriever.retrieve("promotion manager guide", regular_non_manager, ContextPlan(1, "policy_question"), limit=20)

    assert any("manager_playbook" in chunk.source_path for chunk in manager_chunks)
    assert all("manager_playbook" not in chunk.source_path for chunk in non_manager_chunks)


def test_regular_employee_cannot_retrieve_maya_evidence_or_infer_facts() -> None:
    retriever = InMemoryEvidenceRetriever()
    caller = CallerContext("E009", "UG_REGULAR")
    try:
        retriever.assert_authorized(caller, "E001")
    except PermissionDenied as exc:
        message = str(exc)
    else:
        raise AssertionError("expected PermissionDenied")

    assert "Maya" not in message
    assert "Customer Success Manager" not in message
    assert "2026-08-01" not in message

    plan = ContextPlan(1, "offer_letter", required_evidence=("maya_cohen_offer_letter.md",))
    chunks = retriever.retrieve("Maya offer letter day one systems", caller, plan)
    assert not chunks


def test_tool_matrix_exposes_expected_reads_and_no_direct_write() -> None:
    assert validate_tool_matrix() == []
