from __future__ import annotations

from dataclasses import dataclass

from maya import ops


WRITE_TOOLS = frozenset({"create_access_request", "create_ticket"})


@dataclass(frozen=True)
class WriteGateDecision:
    released: bool
    tool_name: str
    request_id: str
    approval_ids: tuple[str, ...]
    reason: str


class RecordedApprovalWriteGate:
    """Fail-closed authorization based only on durable approval rows.

    User or model text is intentionally absent from this API. Text may decide that
    an action should be proposed, but it cannot authorize a write.
    """

    def __init__(self, operations=ops) -> None:
        self.operations = operations

    def evaluate(self, tool_name: str, request_id: str) -> WriteGateDecision:
        if tool_name not in WRITE_TOOLS:
            return WriteGateDecision(False, tool_name, request_id, (), "Tool is not an allow-listed write.")

        approvals = self.operations.list_approvals(request_id)
        approval_ids = tuple(item["approval_id"] for item in approvals)
        if not approvals:
            return WriteGateDecision(False, tool_name, request_id, (), "No recorded approval exists.")

        rejected = [item for item in approvals if item["status"] == "rejected"]
        if rejected:
            return WriteGateDecision(False, tool_name, request_id, approval_ids, "A recorded approval rejected the request.")

        outstanding = [item for item in approvals if item["status"] != "approved"]
        if outstanding:
            return WriteGateDecision(False, tool_name, request_id, approval_ids, "Recorded approvals are still outstanding.")

        return WriteGateDecision(True, tool_name, request_id, approval_ids, "Every required approval is recorded as approved.")

    def resume_access_handoff(self, handoff_id: str) -> tuple[WriteGateDecision, dict | None]:
        decision = self.evaluate("create_access_request", handoff_id)
        if not decision.released:
            return decision, None
        return decision, ops.create_access_request_from_approved_handoff(handoff_id)
