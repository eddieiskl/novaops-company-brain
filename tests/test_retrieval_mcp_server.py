from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrieval_mcp_server import list_evidence_collections, retrieve_evidence


def test_retrieval_mcp_lists_read_only_collections() -> None:
    collections = list_evidence_collections()

    assert "employment" in collections
    assert "policies" in collections


def test_retrieval_mcp_denies_regular_employee_maya_evidence() -> None:
    chunks = retrieve_evidence(
        query="Maya offer letter",
        caller_employee_id="E009",
        caller_user_group="UG_REGULAR",
    )

    assert chunks == []
