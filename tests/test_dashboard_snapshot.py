from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya.dashboard import build_dashboard_snapshot
from maya.retrieval import InMemoryEvidenceRetriever


def test_dashboard_snapshot_summarizes_s2_readiness() -> None:
    snapshot = build_dashboard_snapshot(InMemoryEvidenceRetriever())

    assert snapshot["employee"]["name"] == "Maya Cohen"
    assert snapshot["readiness"]["blocked"] >= 1
    assert any(item["name"] == "Webex license" for item in snapshot["blocked_items"])
    assert any(source["source_path"] == "documents/employment/maya_cohen_offer_letter.md" for source in snapshot["evidence_sources"])
    assert len(snapshot["handoffs"]) == 1
    assert len(snapshot["turns"]) == 12


def test_dashboard_snapshot_can_build_from_worker_threads() -> None:
    def build() -> str:
        snapshot = build_dashboard_snapshot(InMemoryEvidenceRetriever())
        return snapshot["handoffs"][0]["request_id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        request_ids = list(executor.map(lambda _: build(), range(2)))

    assert request_ids == ["WX-001", "WX-001"]
