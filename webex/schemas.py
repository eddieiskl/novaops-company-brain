from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


DecisionStatus = Literal[
    "blocked_pending_approvals",
    "approved_pending_assignment",
    "refused",
    "needs_clarification",
]


@dataclass(frozen=True)
class ApprovalUpdate:
    approval_id: str
    status: Literal["approved", "rejected"]
    actor_employee_id: str
    reason: str


@dataclass(frozen=True)
class WebexCaseInput:
    request: str
    employee_id: str = "E010"
    software: str = "Webex"
    caller_employee_id: str = "E010"
    caller_user_group: str = "UG_REGULAR"
    approval_updates: tuple[ApprovalUpdate, ...] = ()


@dataclass
class AccessDecision:
    employee_id: str
    employee_name: str
    software: str
    eligible_by_role: bool
    status: DecisionStatus
    granted_access: bool
    existing_ticket_id: str | None
    existing_request_id: str | None
    seat_limit: int | None
    active_seats: int | None
    seats_available: int | None
    approvals: list[dict] = field(default_factory=list)
    persisted_approvals: list[dict] = field(default_factory=list)
    operational_tool_calls: list[str] = field(default_factory=list)
    observed_facts: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    blocking_reason: str | None = None
    answer: str = ""

    def trace_projection(self) -> dict:
        return {
            "employee": {
                "id": self.employee_id,
                "name": self.employee_name,
                "eligible_by_role": self.eligible_by_role,
            },
            "software": self.software,
            "decision": {
                "status": self.status,
                "granted_access": self.granted_access,
                "answer": self.answer,
            },
            "existing_ticket_id": self.existing_ticket_id,
            "existing_request_id": self.existing_request_id,
            "subscription": {
                "seat_limit": self.seat_limit,
                "active_seats": self.active_seats,
                "seats_available": self.seats_available,
            },
            "approvals": self.approvals,
            "persisted_approvals": self.persisted_approvals,
            "operational_tool_calls": self.operational_tool_calls,
            "observed_facts": self.observed_facts,
            "actions_taken": self.actions_taken,
            "recommended_next_steps": self.recommended_next_steps,
            "blocking_reason": self.blocking_reason,
        }
