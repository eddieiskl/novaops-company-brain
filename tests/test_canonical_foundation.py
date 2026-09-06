from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import ops
from maya.retrieval import InMemoryEvidenceRetriever
from maya.schemas import CallerContext, ContextPlan
from retrieval_mcp_server import inspect_software_seat_assignments


def test_canonical_database_is_durable_and_reseedable(tmp_path, monkeypatch) -> None:
    database = tmp_path / "novaops.sqlite3"
    monkeypatch.setenv("NOVAOPS_DB_PATH", str(database))
    ops.reset_conn()

    assert database.exists()
    assert ops.get_employee("E001")[0]["full_name"] == "Maya Cohen"

    ops.conn().execute("UPDATE approvals SET status = 'approved' WHERE approval_id = 'AP001'")
    ops.conn().commit()
    ops.reset_conn(reseed=False)
    assert ops.list_approvals("AR001")[0]["status"] == "approved"

    ops.reset_conn()
    assert ops.list_approvals("AR001")[0]["status"] == "needed"


def test_canonical_corpus_preserves_manager_audience_metadata() -> None:
    retriever = InMemoryEvidenceRetriever()
    manager_chunks = [chunk for chunk in retriever.chunks if chunk.collection == "manager_playbook"]
    handbook_chunks = [chunk for chunk in retriever.chunks if chunk.collection == "handbook"]

    assert manager_chunks
    assert handbook_chunks
    assert {chunk.audience for chunk in manager_chunks} == {"manager"}
    assert {chunk.audience for chunk in handbook_chunks} == {"all"}


def test_retrieval_filter_blocks_manager_content_before_ranking() -> None:
    retriever = InMemoryEvidenceRetriever()
    caller = CallerContext("E001", "UG_REGULAR")
    plan = ContextPlan(1, "policy_question", subject_employee_id="E001")

    chunks = retriever.retrieve("promotion April October manager guide feedback", caller, plan, limit=30)

    assert any(chunk.source_path.endswith("handbook/making-a-career.md") for chunk in chunks)
    assert all("manager_playbook/" not in chunk.source_path for chunk in chunks)


def test_seat_assignment_tool_reports_the_data_gap_without_guessing() -> None:
    ops.reset_conn()
    result = inspect_software_seat_assignments("Webex", "E018")

    assert result["assignments_recorded"] is False
    assert result["authoritative_assignment_source"] is None
    assert result["subscription"]["seat_limit"] == 40
    assert result["subscription"]["active_seats"] == 42
    assert "entitlement is not proof" in result["limitation"]
