from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from company_brain.instrumentation import observe

from .adapters import MockNotificationAdapter, MockProviderEmailAdapter, NotificationAdapter, ProviderEmailAdapter
from .extractor import ProviderDecisionExtractor, ProviderRenewalDecision
from .schemas import InternalApprovalEvent, RenewalResult
from .store import RenewalStore


ROOT = Path(__file__).resolve().parents[1]


class RenewalWorkflow:
    """Schedule/event-driven renewal workflow with a deterministic write gate."""

    def __init__(
        self,
        store: RenewalStore,
        notifications: NotificationAdapter,
        provider_email: ProviderEmailAdapter,
        extractor: ProviderDecisionExtractor,
    ) -> None:
        self.store = store
        self.notifications = notifications
        self.provider_email = provider_email
        self.extractor = extractor

    def start(self, as_of: str) -> RenewalResult:
        with observe("renewal_schedule", input={"as_of": as_of}) as span:
            due = self.store.due_webex(as_of)
            if due is None:
                result = RenewalResult("none", "completed", "no_contract_due", "No Webex contract is inside the review window.")
                span.update(output=asdict(result))
                return result
            run = self.store.create_run(due, as_of)
            message_id = self.notifications.send(
                run_id=run["run_id"],
                idempotency_key=f"{run['run_id']}:internal-approval",
                channel="slack",
                recipient=run["approver_id"],
                kind="internal_approval_request",
                subject=f"Urgent Webex renewal decision for {due['contract_id']}",
                body=(
                    f"Review Webex contract {due['contract_id']} ending {due['end_date']}. "
                    f"Current subscription is {due['active_seats']} active seats against {due['seat_limit']}; "
                    f"annual cost is USD {due['subscription_cost']}."
                ),
                created_at=f"{as_of}T00:00:00Z",
            )
            result = RenewalResult(
                run["run_id"],
                "pending",
                run["stage"],
                f"Renewal run {run['run_id']} is persisted and awaiting decision from {run['approver_id']}.",
                outbox_message_ids=[message_id],
            )
            span.update(output=asdict(result), metadata={"urgent": bool(run["urgent"])})
            return result

    def handle_internal_event(self, event: InternalApprovalEvent) -> RenewalResult:
        with observe("renewal_internal_approval", input=asdict(event)) as span:
            run = self.store.get_run(event.renewal_run_id)
            if run is None:
                raise ValueError(f"Unknown renewal run: {event.renewal_run_id}")
            if self.store.processed(event.event_id):
                result = self._current_result(run["run_id"], "Approval event replayed; no duplicate action was created.")
                span.update(output=asdict(result), metadata={"replayed": True})
                return result
            if event.contract_id != run["contract_id"]:
                raise ValueError("Approval event contract does not match the renewal run.")
            if event.actor_employee_id != run["approver_id"]:
                raise PermissionError(f"Renewal decision is assigned to {run['approver_id']}, not {event.actor_employee_id}.")

            self.store.record_internal_decision(event)
            message_ids: list[str] = []
            if event.decision == "approved":
                message_ids.append(self._send_provider_request(run, event.decided_at))
            self.store.mark_processed(event.event_id, run["run_id"], "internal_approval", event.decided_at)
            result = self._current_result(
                run["run_id"],
                "Internal approval persisted; provider confirmation is now required."
                if event.decision == "approved"
                else "The renewal was rejected internally; no provider request or business update was made.",
            )
            result.outbox_message_ids = message_ids
            span.update(output=asdict(result), metadata={"replayed": False})
            return result

    def handle_provider_reply(self, run_id: str, fixture_id: str, provider_reply: str | None = None) -> RenewalResult:
        event_id = f"provider:{fixture_id}"
        with observe("renewal_provider_reply", input={"run_id": run_id, "fixture_id": fixture_id}) as span:
            run = self.store.get_run(run_id)
            if run is None:
                raise ValueError(f"Unknown renewal run: {run_id}")
            if self.store.processed(event_id):
                result = self._current_result(run_id, "Provider reply replayed; no duplicate update or notification was created.")
                span.update(output=asdict(result), metadata={"replayed": True})
                return result
            if run["stage"] != "awaiting_provider_reply" or run["internal_decision"] != "approved":
                raise RuntimeError("Provider reply cannot be applied before the recorded internal approval.")

            reply = provider_reply if provider_reply is not None else self.provider_email.fetch_reply(fixture_id)
            decision = self.extractor.extract(fixture_id, reply)
            timestamp = "2026-07-03T12:45:00Z"
            self.store.record_provider_decision(run_id, fixture_id, decision.as_dict(), timestamp)
            allowed, reason = self._allow_apply(run, decision)
            notified: list[str] = []
            if allowed:
                with observe("renewal_apply_update", input=decision.as_dict()) as apply_span:
                    applied = self.store.apply_approved(run_id, decision, timestamp)
                    if applied:
                        notified = self._notify_blocked_users(run_id, timestamp)
                    apply_span.update(output={"applied": applied, "notified_employee_ids": notified})
                answer = (
                    f"Provider confirmation {decision.confirmation_id} was validated and applied: Webex now has "
                    f"{decision.new_seat_limit} seats at USD {decision.annual_cost_usd} through {decision.term_end_date}. "
                    f"Blocked employees were notified that the blocker changed; access was not granted."
                )
            else:
                applied = False
                self.store.mark_needs_human(run_id, timestamp)
                self.notifications.send(
                    run_id=run_id,
                    idempotency_key=f"{run_id}:provider-review:{fixture_id}",
                    channel="slack",
                    recipient=run["approver_id"],
                    kind="provider_review_required",
                    subject=f"Human review required for {run['contract_id']}",
                    body=f"Provider reply {fixture_id} was not eligible for automatic application: {reason}.",
                    created_at=timestamp,
                )
                answer = f"Provider reply {fixture_id} requires human review; no contract or subscription fields were changed. {reason}"
            self.store.mark_processed(event_id, run_id, "provider_reply", timestamp)
            result = self._current_result(run_id, answer, decision=decision)
            result.applied = applied
            result.subscription_updated = applied
            result.notified_employee_ids = notified
            span.update(output=asdict(result), metadata={"replayed": False, "write_gate_reason": reason})
            return result

    def _send_provider_request(self, run: dict[str, Any], timestamp: str) -> str:
        db = self.store.db
        facts = db.execute(
            "SELECT c.end_date, c.renewal_notice_days, c.annual_cost, s.seat_limit, s.active_seats, v.vendor_name "
            "FROM contracts c JOIN software_subscriptions s ON s.contract_id = c.contract_id "
            "JOIN vendors v ON v.vendor_id = c.vendor_id WHERE c.contract_id = ?",
            (run["contract_id"],),
        ).fetchone()
        return self.provider_email.send(
            run_id=run["run_id"],
            recipient="nina.alvarez@webex-vendor.example",
            subject=f"Renewal and 50-seat expansion request — {run['contract_id']}",
            body=(
                f"Please confirm renewal of {facts['vendor_name']} contract {run['contract_id']} after {facts['end_date']} "
                f"and expansion from {facts['seat_limit']} to 50 seats. Current annual cost is USD {facts['annual_cost']}. "
                "Return the final term dates, annual cost, seat limit, and confirmation id."
            ),
            created_at=timestamp,
        )

    def _allow_apply(self, run: dict[str, Any], decision: ProviderRenewalDecision) -> tuple[bool, str]:
        if decision.decision != "approved":
            return False, f"decision={decision.decision}"
        if decision.missing_fields or decision.conditions:
            return False, f"missing={decision.missing_fields}; conditions={decision.conditions}"
        if decision.contract_id != run["contract_id"]:
            return False, "provider contract id does not match the pending run"
        expected = {
            "new_seat_limit": 50,
            "annual_cost_usd": 22000,
            "term_start_date": "2026-07-21",
            "term_end_date": "2027-07-20",
        }
        mismatches = [name for name, value in expected.items() if getattr(decision, name) != value]
        if mismatches or not decision.confirmation_id:
            return False, f"commercial validation failed for {mismatches or ['confirmation_id']}"
        previous_end = self.store.db.execute(
            "SELECT end_date FROM contracts WHERE contract_id = ?", (run["contract_id"],)
        ).fetchone()["end_date"]
        if date.fromisoformat(decision.term_start_date) != date.fromisoformat(previous_end) + timedelta(days=1):
            return False, "renewed term does not start immediately after the current term"
        return True, "complete approved reply matched the pending run and expected commercial terms"

    def _notify_blocked_users(self, run_id: str, timestamp: str) -> list[str]:
        notified: list[str] = []
        for employee in self.store.blocked_employees(run_id):
            message_id = self.notifications.send(
                run_id=run_id,
                idempotency_key=f"{run_id}:blocker-changed:{employee['employee_id']}",
                channel="email",
                recipient=employee["email"],
                kind="blocker_changed",
                subject="Webex seat blocker changed",
                body=(
                    "The Webex contract seat limit was expanded. Your existing access request remains in its "
                    "system-of-record status; this notification does not grant access."
                ),
                created_at=timestamp,
            )
            if self.store.record_notification(run_id, employee["employee_id"], message_id, timestamp):
                notified.append(employee["employee_id"])
        return notified

    def _current_result(
        self,
        run_id: str,
        answer: str,
        *,
        decision: ProviderRenewalDecision | None = None,
    ) -> RenewalResult:
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown renewal run: {run_id}")
        notifications = self.store.notifications(run_id)
        return RenewalResult(
            run_id,
            run["status"],
            run["stage"],
            answer,
            applied=bool(self.store.applied_updates(run_id)),
            subscription_updated=bool(self.store.applied_updates(run_id)),
            notified_employee_ids=[row["employee_id"] for row in notifications],
            outbox_message_ids=[row["message_id"] for row in self.store.outbox(run_id)],
            provider_decision=decision,
        )


def build_renewal_workflow(
    *,
    extractor: ProviderDecisionExtractor | None = None,
    replies: dict[str, str] | None = None,
) -> RenewalWorkflow:
    store = RenewalStore()
    return RenewalWorkflow(
        store,
        MockNotificationAdapter(store),
        MockProviderEmailAdapter(store, replies=replies),
        extractor or ProviderDecisionExtractor(),
    )
