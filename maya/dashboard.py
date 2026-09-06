from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from .graph import MayaAgent
from .ports import FakeWebexPort
from .retrieval import EvidenceRetriever
from .schemas import CallerContext, ChecklistItem, EvidenceCitation


DEFAULT_SESSION = Path(__file__).resolve().parents[1] / "evals" / "context_sessions.json"


def build_dashboard_snapshot(retriever: EvidenceRetriever, session_path: Path = DEFAULT_SESSION) -> dict:
    spec = json.loads(session_path.read_text(encoding="utf-8"))
    caller = CallerContext(**spec["caller"])
    port = FakeWebexPort()
    agent = MayaAgent(retriever, port)
    results = [
        agent.handle_turn_sync(spec["id"], caller, turn["n"], turn["user"])
        for turn in spec["turns"]
    ]
    final = results[-1]
    checklist = final.checklist
    items = checklist.systems + checklist.equipment + checklist.policy_requirements + checklist.blocked_items
    status_counts = Counter(item.status for item in items)
    evidence = _dedupe_citations(checklist.all_citations())
    handoffs = [handoff for result in results for handoff in result.handoffs]

    return {
        "employee": {
            "id": checklist.employee_id,
            "name": checklist.employee_name,
            "role": checklist.role,
            "start_date": checklist.start_date,
            "location": checklist.location,
        },
        "readiness": {
            "total_items": len(items),
            "ready_or_planned": sum(status_counts[status] for status in ("ready", "planned", "required", "pending")),
            "blocked": status_counts["blocked_or_pending"],
            "unresolved": status_counts["unresolved"],
            "finance_required": status_counts["finance_required"],
        },
        "systems": [_item(item) for item in checklist.systems],
        "equipment": [_item(item) for item in checklist.equipment],
        "policy_requirements": [_item(item) for item in checklist.policy_requirements],
        "blocked_items": [_item(item) for item in checklist.blocked_items],
        "evidence_sources": [asdict(citation) for citation in evidence],
        "handoffs": [asdict(handoff) for handoff in handoffs],
        "turns": [
            {
                "turn": result.turn,
                "intent": result.intent,
                "tool_calls": result.operational_tool_calls,
                "handoffs": len(result.handoffs),
                "errors": result.errors,
            }
            for result in results
        ],
        "last_answer": final.answer,
    }


def _item(item: ChecklistItem) -> dict:
    return {
        "name": item.name,
        "status": item.status,
        "detail": item.detail,
        "evidence": [asdict(citation) for citation in item.evidence],
    }


def _dedupe_citations(citations: list[EvidenceCitation]) -> list[EvidenceCitation]:
    by_chunk: dict[str, EvidenceCitation] = {}
    for citation in citations:
        by_chunk.setdefault(citation.chunk_id, citation)
    return list(by_chunk.values())
