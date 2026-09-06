from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from maya import ops
from maya.retrieval import InMemoryEvidenceRetriever
from maya.schemas import CallerContext, ContextPlan
from webex.write_gate import RecordedApprovalWriteGate


retriever = InMemoryEvidenceRetriever()
DOCUMENTS_ROOT = ROOT / "novaops-enterprise-agent-dataset" / "documents"


def list_evidence_collections() -> list[str]:
    """List read-only evidence collections available to Maya."""
    return sorted({chunk.collection for chunk in retriever.chunks})


def retrieve_evidence(
    query: str,
    caller_employee_id: str,
    caller_user_group: str,
    subject_employee_id: str = "E001",
    intent: str = "offer_letter",
    required_evidence: list[str] | None = None,
    limit: int = 4,
) -> list[dict]:
    """Retrieve cited evidence with caller authorization enforced before search."""
    caller = CallerContext(caller_employee_id, caller_user_group)  # type: ignore[arg-type]
    plan = ContextPlan(
        0,
        intent,
        subject_employee_id=subject_employee_id,
        required_evidence=tuple(required_evidence or ()),
    )
    chunks = retriever.retrieve(query, caller, plan, limit=limit)
    return [
        {
            "source_path": chunk.source_path,
            "chunk_id": chunk.chunk_id,
            "collection": chunk.collection,
            "title": chunk.title,
            "text": chunk.text,
            "audience": chunk.audience,
            "sensitivity": chunk.sensitivity,
            "subject_employee_id": chunk.subject_employee_id,
            "update_date": chunk.update_date,
            "citation": chunk.citation().__dict__,
            "score": chunk.score,
        }
        for chunk in chunks
    ]


def list_policies() -> list[str]:
    """List available policy document names."""
    return sorted(path.stem for path in (DOCUMENTS_ROOT / "policies").glob("*.md"))


def get_policy(name: str) -> str:
    """Read one policy by name; use list_policies to discover valid names."""
    path = DOCUMENTS_ROOT / "policies" / f"{name}.md"
    if not path.is_file():
        raise ValueError(f"No policy named {name!r}. Call list_policies for valid names.")
    return path.read_text(encoding="utf-8")


def get_employee(query: str) -> list[dict]:
    """Look up employees by id, email, or partial full name."""
    return ops.get_employee(query)


def list_direct_reports(manager_id: str) -> list[dict]:
    """List employees whose recorded manager_id matches the caller."""
    return ops.list_direct_reports(manager_id)


def list_onboarding_tasks(employee_id: str) -> list[dict]:
    """Read the authoritative onboarding task rows for one employee."""
    return ops.list_onboarding_tasks(employee_id)


def check_asset_inventory(asset_type: str = "", location: str = "") -> list[dict]:
    """Read equipment inventory, optionally filtered by type and location."""
    return ops.check_asset_inventory(asset_type, location)


def check_software_subscription(software: str) -> list[dict]:
    """Read aggregate seat limit, active-seat count, renewal and cost facts."""
    return ops.check_software_subscription(software)


def inspect_software_seat_assignments(software: str, manager_id: str = "") -> dict:
    """Report whether per-employee seat assignments are observable.

    This deliberately returns the dataset limitation instead of treating role
    entitlement as proof that an employee holds a license.
    """
    return ops.inspect_software_seat_assignments(software, manager_id)


def list_employee_tickets(employee_id: str, status: str = "") -> list[dict]:
    """Read existing tickets before any attempt to create a new one."""
    return ops.list_employee_tickets(employee_id, status)


def list_access_requests(employee_id: str, software: str = "") -> list[dict]:
    """Read existing access requests so replays reuse rather than duplicate them."""
    return ops.list_access_requests(employee_id, software)


def list_approvals(request_id: str) -> list[dict]:
    """Read persisted approval records associated with a business request."""
    return ops.list_approvals(request_id)


def record_approval_decision(
    approval_id: str,
    status: str,
    actor_employee_id: str,
    reason: str,
) -> dict:
    """Persist a trusted external approval event after verifying its assigned actor.

    This capability is for the approval-event adapter, not for model tool loadouts.
    """
    return ops.record_approval_decision(approval_id, status, actor_employee_id, reason)


def prepare_access_handoff(
    conversation_id: str,
    subject_employee_id: str,
    software: str,
    business_justification: str,
    caller_employee_id: str,
    idempotency_key: str,
) -> dict:
    """Persist an access intent and its required human approval, then stop.

    This does not create an access request and never grants access.
    """
    return ops.prepare_access_handoff(
        conversation_id=conversation_id,
        subject_employee_id=subject_employee_id,
        software=software,
        business_justification=business_justification,
        caller_employee_id=caller_employee_id,
        idempotency_key=idempotency_key,
    )


def resume_access_handoff(handoff_id: str) -> dict:
    """Resume a persisted handoff; release its write only on recorded approval."""
    gate, request = RecordedApprovalWriteGate().resume_access_handoff(handoff_id)
    return {
        "released": gate.released,
        "reason": gate.reason,
        "approval_ids": list(gate.approval_ids),
        "access_request": request,
    }


def build_server():
    from mcp.server.fastmcp import FastMCP

    host = os.getenv("NOVAOPS_MCP_HOST", "127.0.0.1")
    port = int(os.getenv("NOVAOPS_MCP_PORT", "9880"))
    mcp = FastMCP("novaops-company-brain", host=host, port=port)
    for tool in (
        list_evidence_collections,
        retrieve_evidence,
        list_policies,
        get_policy,
        get_employee,
        list_direct_reports,
        list_onboarding_tasks,
        check_asset_inventory,
        check_software_subscription,
        inspect_software_seat_assignments,
        list_employee_tickets,
        list_access_requests,
        list_approvals,
        record_approval_decision,
        prepare_access_handoff,
        resume_access_handoff,
    ):
        mcp.tool()(tool)
    return mcp


if __name__ == "__main__":
    server = build_server()
    print(
        "NovaOps company-brain MCP server -> "
        f"http://{os.getenv('NOVAOPS_MCP_HOST', '127.0.0.1')}:{os.getenv('NOVAOPS_MCP_PORT', '9880')}/mcp"
    )
    server.run(transport="streamable-http")
