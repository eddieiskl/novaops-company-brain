from __future__ import annotations

from typing import Any, Protocol

import retrieval_mcp_server as local_server
from maya.schemas import CallerContext, ContextPlan, EvidenceChunk
from maya.schemas import PendingAccessResult, WebexHandoff

from .mcp_client import MCPToolClient


class ToolGateway(Protocol):
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        ...


class LocalToolGateway:
    """In-process MCP-server adapter used only for deterministic tests."""

    _TOOLS = {
        name: getattr(local_server, name)
        for name in (
            "retrieve_evidence",
            "get_employee",
            "list_direct_reports",
            "list_onboarding_tasks",
            "check_asset_inventory",
            "check_software_subscription",
            "inspect_software_seat_assignments",
            "list_employee_tickets",
            "list_access_requests",
            "list_approvals",
            "record_approval_decision",
            "prepare_access_handoff",
            "resume_access_handoff",
        )
    }

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        try:
            tool = self._TOOLS[name]
        except KeyError as exc:
            raise ValueError(f"Unknown local MCP tool: {name}") from exc
        return tool(**(arguments or {}))


class RemoteMCPToolGateway:
    def __init__(self, url: str = "http://127.0.0.1:9880/mcp") -> None:
        self.client = MCPToolClient(url)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self.client.call_sync(name, arguments)


class GatewayOperations:
    """Typed-looking operations facade whose calls always cross one tool gateway."""

    def __init__(self, gateway: ToolGateway) -> None:
        self.gateway = gateway

    def get_employee(self, query: str) -> list[dict]:
        return self.gateway.call("get_employee", {"query": query})

    def list_direct_reports(self, manager_id: str) -> list[dict]:
        return self.gateway.call("list_direct_reports", {"manager_id": manager_id})

    def list_onboarding_tasks(self, employee_id: str) -> list[dict]:
        return self.gateway.call("list_onboarding_tasks", {"employee_id": employee_id})

    def check_asset_inventory(self, asset_type: str = "", location: str = "") -> list[dict]:
        return self.gateway.call("check_asset_inventory", {"asset_type": asset_type, "location": location})

    def check_software_subscription(self, software: str) -> list[dict]:
        return self.gateway.call("check_software_subscription", {"software": software})

    def inspect_software_seat_assignments(self, software: str, manager_id: str = "") -> dict:
        return self.gateway.call("inspect_software_seat_assignments", {"software": software, "manager_id": manager_id})

    def list_employee_tickets(self, employee_id: str, status: str = "") -> list[dict]:
        return self.gateway.call("list_employee_tickets", {"employee_id": employee_id, "status": status})

    def list_access_requests(self, employee_id: str, software: str = "") -> list[dict]:
        return self.gateway.call("list_access_requests", {"employee_id": employee_id, "software": software})

    def list_approvals(self, request_id: str) -> list[dict]:
        return self.gateway.call("list_approvals", {"request_id": request_id})

    def record_approval_decision(self, approval_id: str, status: str, actor_employee_id: str, reason: str) -> dict:
        return self.gateway.call(
            "record_approval_decision",
            {
                "approval_id": approval_id,
                "status": status,
                "actor_employee_id": actor_employee_id,
                "reason": reason,
            },
        )


class GatewayEvidenceRetriever:
    def __init__(self, gateway: ToolGateway) -> None:
        self.gateway = gateway

    def assert_authorized(self, caller: CallerContext, subject_employee_id: str) -> None:
        # Authorization is enforced inside retrieve_evidence on the MCP server. The
        # local preflight mirrors its cross-employee rule without exposing data.
        if caller.user_group not in {"UG_HR", "UG_IT"} and caller.employee_id != subject_employee_id:
            from maya.retrieval import PermissionDenied

            raise PermissionDenied("Caller is not authorized to retrieve the requested restricted evidence.")

    def retrieve(self, query: str, caller: CallerContext, plan: ContextPlan, limit: int = 6) -> list[EvidenceChunk]:
        rows = self.gateway.call(
            "retrieve_evidence",
            {
                "query": query,
                "caller_employee_id": caller.employee_id,
                "caller_user_group": caller.user_group,
                "subject_employee_id": plan.subject_employee_id,
                "intent": plan.intent,
                "limit": limit,
            },
        )
        chunks: list[EvidenceChunk] = []
        for row in rows:
            citation = row.get("citation", {})
            chunks.append(
                EvidenceChunk(
                    source_path=row["source_path"],
                    chunk_id=row["chunk_id"],
                    collection=row["collection"],
                    title=row["title"],
                    text=row.get("text", ""),
                    audience=row.get("audience", "all"),
                    sensitivity=row.get("sensitivity", "internal"),
                    subject_employee_id=row.get("subject_employee_id"),
                    update_date=row.get("update_date"),
                    score=float(row.get("score", 0.0)),
                )
            )
        return chunks


class GatewayWebexPort:
    """Persists Maya's typed handoff through the selected MCP boundary."""

    def __init__(self, gateway: ToolGateway) -> None:
        self.gateway = gateway

    async def request_access(self, handoff: WebexHandoff) -> PendingAccessResult:
        row = self.gateway.call(
            "prepare_access_handoff",
            {
                "conversation_id": handoff.idempotency_key.rsplit(":", 1)[-1],
                "subject_employee_id": handoff.employee_id,
                "software": handoff.software,
                "business_justification": handoff.business_reason,
                "caller_employee_id": handoff.caller_employee_id,
                "idempotency_key": handoff.idempotency_key,
            },
        )
        return PendingAccessResult(
            request_id=row["handoff_id"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
        )
