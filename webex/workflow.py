from __future__ import annotations

import json

from maya import ops

from .schemas import AccessDecision, WebexCaseInput


class WebexAccessWorkflow:
    """Deterministic baseline for Rachel Stein's Webex access issue.

    The workflow is intentionally conservative: it may reuse existing operational
    records and persist explicit approval updates, but it never grants access while
    the subscription is over limit or approvals are still outstanding.
    """

    def __init__(self, operations=ops) -> None:
        self.ops = operations

    def handle(self, case: WebexCaseInput) -> AccessDecision:
        calls: list[str] = []

        employee = self._first(self.ops.get_employee(case.employee_id))
        calls.append("get_employee")
        if employee is None:
            return AccessDecision(
                employee_id=case.employee_id,
                employee_name="unknown",
                software=case.software,
                eligible_by_role=False,
                status="needs_clarification",
                granted_access=False,
                existing_ticket_id=None,
                existing_request_id=None,
                seat_limit=None,
                active_seats=None,
                seats_available=None,
                operational_tool_calls=calls,
                answer=f"I could not find employee {case.employee_id}; I need the correct employee id before changing access.",
            )

        tickets = self.ops.list_employee_tickets(case.employee_id)
        calls.append("list_employee_tickets")
        subscription = self._first(self.ops.check_software_subscription(case.software))
        calls.append("check_software_subscription")
        access_requests = self.ops.list_access_requests(case.employee_id, case.software)
        calls.append("list_access_requests")

        existing_ticket = self._matching_ticket(tickets, case.software)
        existing_request = access_requests[0] if access_requests else None
        approvals = self.ops.list_approvals(existing_request["request_id"]) if existing_request else []
        if existing_request:
            calls.append("list_approvals")

        persisted = []
        for update in case.approval_updates:
            persisted.append(
                self.ops.record_approval_decision(
                    update.approval_id,
                    update.status,
                    update.actor_employee_id,
                    update.reason,
                )
            )
            calls.append("record_approval_decision")
        if persisted and existing_request:
            approvals = self.ops.list_approvals(existing_request["request_id"])
            calls.append("list_approvals")

        eligible = self._eligible(employee, case.software)
        outstanding = [a for a in approvals if a["status"] in {"needed", "pending"}]
        rejected = [a for a in approvals if a["status"] == "rejected"]
        over_limit = bool(subscription and subscription["over_limit"])

        if not eligible:
            status = "refused"
            reason = f"{employee['full_name']} is not role-eligible for {case.software}."
        elif rejected:
            status = "refused"
            reason = f"{case.software} access is refused because approval {rejected[0]['approval_id']} was rejected."
        elif over_limit or outstanding:
            status = "blocked_pending_approvals"
            reason = self._blocked_reason(case.software, subscription, existing_request, outstanding)
        else:
            status = "approved_pending_assignment"
            reason = f"{case.software} access is eligible and approvals are complete, but this baseline still does not assign the license directly."

        decision = AccessDecision(
            employee_id=employee["employee_id"],
            employee_name=employee["full_name"],
            software=case.software,
            eligible_by_role=eligible,
            status=status,
            granted_access=False,
            existing_ticket_id=existing_ticket["ticket_id"] if existing_ticket else None,
            existing_request_id=existing_request["request_id"] if existing_request else None,
            seat_limit=subscription["seat_limit"] if subscription else None,
            active_seats=subscription["active_seats"] if subscription else None,
            seats_available=subscription["seats_available"] if subscription else None,
            approvals=approvals,
            persisted_approvals=persisted,
            operational_tool_calls=calls,
            observed_facts=self._observed_facts(employee, subscription, existing_ticket, existing_request, approvals),
            actions_taken=self._actions_taken(existing_ticket, existing_request, persisted),
            recommended_next_steps=self._next_steps(over_limit, outstanding, rejected),
            blocking_reason=reason if status in {"blocked_pending_approvals", "refused"} else None,
        )
        decision.answer = self._answer(decision, reason)
        return decision

    @staticmethod
    def _observed_facts(
        employee: dict,
        subscription: dict | None,
        ticket: dict | None,
        request: dict | None,
        approvals: list[dict],
    ) -> list[str]:
        facts = [f"{employee['full_name']} is employee {employee['employee_id']} in {employee['role']}."]
        if subscription:
            facts.append(
                f"Webex records {subscription['active_seats']} active seats against a {subscription['seat_limit']}-seat limit."
            )
        if ticket:
            facts.append(f"Ticket {ticket['ticket_id']} already exists with status {ticket['status']}.")
        if request:
            facts.append(f"Access request {request['request_id']} already exists with status {request['status']}.")
        if approvals:
            facts.append("Approval state: " + ", ".join(f"{item['approval_id']}={item['status']}" for item in approvals) + ".")
        return facts

    @staticmethod
    def _actions_taken(ticket: dict | None, request: dict | None, persisted: list[dict]) -> list[str]:
        actions: list[str] = []
        if ticket:
            actions.append(f"Reused existing ticket {ticket['ticket_id']}; no duplicate ticket was created.")
        if request:
            actions.append(f"Reused existing access request {request['request_id']}; no duplicate request was created.")
        actions.extend(f"Recorded approval decision {item['approval_id']}={item['status']}." for item in persisted)
        return actions

    @staticmethod
    def _next_steps(over_limit: bool, outstanding: list[dict], rejected: list[dict]) -> list[str]:
        if rejected:
            return ["A human owner must review the rejection before any new request is proposed."]
        steps: list[str] = []
        if outstanding:
            steps.append("Wait for the assigned approvers to record their decisions.")
        if over_limit:
            steps.append("Resolve the Webex contract seat overage before license assignment.")
        if not steps:
            steps.append("IT may assign the license through the system of record; this workflow does not grant access.")
        return steps

    @staticmethod
    def _first(rows: list[dict]) -> dict | None:
        return rows[0] if rows else None

    @staticmethod
    def _matching_ticket(tickets: list[dict], software: str) -> dict | None:
        needle = software.lower()
        return next(
            (
                ticket
                for ticket in tickets
                if needle in f"{ticket['subcategory']} {ticket['subject']}".lower()
            ),
            None,
        )

    @staticmethod
    def _eligible(employee: dict, software: str) -> bool:
        try:
            allowed = json.loads(employee["systems_allowed_by_role"])
        except json.JSONDecodeError:
            allowed = []
        return any(str(item).lower() == software.lower() for item in allowed)

    @staticmethod
    def _blocked_reason(
        software: str,
        subscription: dict | None,
        existing_request: dict | None,
        outstanding: list[dict],
    ) -> str:
        pieces = []
        if subscription and subscription["over_limit"]:
            pieces.append(
                f"{software} has {subscription['active_seats']} active seats against a "
                f"{subscription['seat_limit']}-seat limit"
            )
        if existing_request:
            pieces.append(f"existing request {existing_request['request_id']} remains {existing_request['status']}")
        if outstanding:
            ids = ", ".join(a["approval_id"] for a in outstanding)
            pieces.append(f"approval still needed: {ids}")
        return "; ".join(pieces) + "."

    @staticmethod
    def _answer(decision: AccessDecision, reason: str) -> str:
        ticket = f" ticket {decision.existing_ticket_id}" if decision.existing_ticket_id else " the existing ticket"
        request = (
            f" and request {decision.existing_request_id}"
            if decision.existing_request_id
            else ""
        )
        return (
            f"{decision.employee_name}'s {decision.software} access is not granted. "
            f"I reused{ticket}{request}. {reason}"
        )
