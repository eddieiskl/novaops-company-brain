from __future__ import annotations
from dataclasses import asdict
from datetime import date, datetime, timedelta
from email import message_from_string
from email.utils import parsedate_to_datetime
from functools import wraps
import json
from pathlib import Path
from typing import Any
from company_brain.instrumentation import observe
from .adapters import (
    MockNotificationAdapter,
    MockProviderEmailAdapter,
    NotificationAdapter,
    ProviderEmailAdapter,
)
from .extractor import ProviderDecisionExtractor, ProviderRenewalDecision
from .schemas import InternalApprovalEvent, RenewalResult
from .store import RenewalStore

ROOT = Path(__file__).resolve().parents[1]


def transaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.store.atomic():
            return method(self, *args, **kwargs)

    return wrapped


class RenewalWorkflow:
    """Local schedule/event workflow. Adapters enqueue; they never send externally."""

    def __init__(
        self, store, notifications, provider_email, extractor, security_reviewer_id=None
    ):
        self.store, self.notifications, self.provider_email, self.extractor = (
            store,
            notifications,
            provider_email,
            extractor,
        )
        # Required explicit configuration: the supplied dataset has no security reviewer assignment.
        self.security_reviewer_id = security_reviewer_id

    @transaction
    def scan(self, as_of):
        today = date.fromisoformat(as_of)
        rows = self.store.db.execute(
            """SELECT c.*,s.subscription_id,s.seat_limit,s.active_seats,
          s.annual_cost AS subscription_cost,d.default_manager_id AS approver_id,sys.system_name,v.vendor_name
          FROM contracts c LEFT JOIN software_subscriptions s ON s.contract_id=c.contract_id
          LEFT JOIN departments d ON d.department_id=c.owner_department_id
          JOIN systems sys ON sys.system_id=c.system_id JOIN vendors v ON v.vendor_id=c.vendor_id"""
        ).fetchall()
        reviews = []
        memo = (
            ROOT
            / "novaops-enterprise-agent-dataset/documents/internal_memos/contract_owner_cleanup_memo.md"
        )
        memo_text = memo.read_text()
        for row in rows:
            facts = dict(row)
            end = date.fromisoformat(facts["end_date"])
            notice = end - timedelta(days=facts["renewal_notice_days"])
            facts.update(
                review_open=(end - timedelta(days=90)).isoformat(),
                notice_deadline=notice.isoformat(),
                expired=today > end,
                urgent=today >= notice - timedelta(days=45),
                in_review=today >= end - timedelta(days=90),
            )
            facts["blocked_demand"] = self.store.db.execute(
                "SELECT COUNT(*) FROM access_requests WHERE system_id=? AND status='blocked'",
                (facts["system_id"],),
            ).fetchone()[0]
            facts["approvals"] = [
                dict(r)
                for r in self.store.db.execute(
                    "SELECT a.* FROM approvals a JOIN access_requests ar ON ar.request_id=a.request_id WHERE ar.system_id=?",
                    (facts["system_id"],),
                )
            ]
            conflict = f"{facts['system_name']} should be" in memo_text
            facts["owner_conflict"] = conflict
            action = "renew_as_is"
            rationale = "Review existing commitment; no automatic commercial decision."
            if conflict:
                action = "escalate"
                rationale = (
                    "Owner memo conflicts with database; require a source/owner ruling."
                )
            elif facts["seat_limit"] is None:
                action = "escalate"
                rationale = "Subscription facts missing."
            elif facts["active_seats"] > facts["seat_limit"] or facts["blocked_demand"]:
                action = "expand"
                rationale = "Active usage or blocked demand warrants expansion review."
            elif facts["active_seats"] < facts["seat_limit"]:
                action = "reduce"
                rationale = (
                    "Unused capacity warrants review, not automatic cancellation."
                )
            recommendation = {
                "action": action,
                "rationale": rationale,
                "uncertainty": "Future demand, owner decisions and clearances require review.",
                "owner": facts["approver_id"],
                "next_action": (
                    "Resolve ownership conflict"
                    if conflict
                    else "Review recommendation and required clearances"
                ),
                "evidence": [
                    f"database/contracts/{facts['contract_id']}",
                    f"database/software_subscriptions/{facts['subscription_id']}",
                    str(memo.relative_to(ROOT)),
                ],
            }
            self.store.db.execute(
                "INSERT OR REPLACE INTO renewal_portfolio_reviews VALUES (?,?,?,?)",
                (
                    facts["contract_id"],
                    as_of,
                    json.dumps(facts, sort_keys=True),
                    json.dumps(recommendation, sort_keys=True),
                ),
            )
            if facts["in_review"]:
                reviews.append({"facts": facts, "recommendation": recommendation})
        return reviews

    @transaction
    def start(self, as_of):
        date.fromisoformat(as_of)
        with observe("renewal_schedule", input={"as_of": as_of}) as span:
            self.activate_due(as_of)
            reviews = self.scan(as_of)
            due = next(
                (r for r in reviews if r["facts"]["contract_id"] == "C001"), None
            )
            # Preserve the public Webex entrypoint; scan() returns every portfolio recommendation.
            existing = self.store.get_run("RR-WEBEX-2026")
            if existing:
                result = self._current_result(
                    existing["run_id"],
                    existing.get("reason") or "Existing renewal state retained.",
                )
            elif due:
                run = self.store.create_run(due["facts"], as_of)
                self.store.db.execute(
                    "UPDATE renewal_runs SET recommendation_json=?,reason=?,next_action=? WHERE run_id=?",
                    (
                        json.dumps(due["recommendation"]),
                        due["recommendation"]["rationale"],
                        "IT approval with scope, Finance hold resolution, and security review required",
                        run["run_id"],
                    ),
                )
                self.notifications.send(
                    run_id=run["run_id"],
                    idempotency_key=run["run_id"] + ":internal-approval",
                    channel="slack",
                    recipient=run["approver_id"],
                    kind="internal_approval_request",
                    subject="Webex renewal review",
                    body=json.dumps(due, sort_keys=True),
                    created_at=as_of + "T00:00:00Z",
                )
                result = self._current_result(
                    run["run_id"],
                    "Expansion recommendation persisted; scoped approval and clearances required.",
                )
            else:
                result = RenewalResult(
                    "none",
                    "completed",
                    "no_contract_due",
                    "No Webex contract is inside the review window.",
                )
            span.update(output=asdict(result))
            return result

    @staticmethod
    def _validate_scope(scope):
        required = {
            "action",
            "new_seat_limit",
            "annual_cost_ceiling_usd",
            "term_start_date",
            "term_end_date",
        }
        if not isinstance(scope, dict) or set(scope) != required:
            raise ValueError(
                "Approval must explicitly include action, seats, price ceiling and term"
            )
        if scope["action"] not in {"renew", "expand", "reduce"}:
            raise ValueError("Unsupported approval action")
        for key in ("new_seat_limit", "annual_cost_ceiling_usd"):
            if type(scope[key]) is not int or scope[key] <= 0:
                raise ValueError("Scope limits must be positive integers")
        if date.fromisoformat(scope["term_start_date"]) >= date.fromisoformat(
            scope["term_end_date"]
        ):
            raise ValueError("Invalid approved term")

    def _preconditions(self, run):
        clear = self.store.clearances(run["run_id"])
        return bool(
            run["internal_decision"] == "approved"
            and run["approved_scope_json"]
            and all(
                clear.get(k, {}).get("decision") == "approved"
                for k in ("finance_clearance", "security_clearance")
            )
        )

    @transaction
    def handle_internal_event(self, event):
        with observe("renewal_internal_approval", input=asdict(event)) as span:
            run = self.store.get_run(event.renewal_run_id)
            if not run:
                raise ValueError("Unknown renewal run")
            if event.contract_id != run["contract_id"]:
                raise ValueError("Contract mismatch")
            if event.decision not in {"approved", "rejected"}:
                raise ValueError("Invalid decision")
            datetime.fromisoformat(event.decided_at.replace("Z", "+00:00"))
            if event.decided_at[:10] < run["as_of_date"]:
                raise ValueError("Decision predates the run")
            allowed = {
                "internal_approval": run["approver_id"],
                "finance_clearance": self.store.db.execute(
                    "SELECT approver_id FROM approvals WHERE approval_id='AP002'"
                ).fetchone()[0],
                "security_clearance": self.security_reviewer_id,
            }
            if (
                event.event_type not in allowed
                or not allowed[event.event_type]
                or event.actor_employee_id != allowed[event.event_type]
            ):
                raise PermissionError("Actor is not assigned to this decision type")
            employee = self.store.db.execute(
                "SELECT status FROM employees WHERE employee_id=?",
                (event.actor_employee_id,),
            ).fetchone()
            if not employee or employee["status"] != "active":
                raise PermissionError("Decision actor is not active")
            if not self.store.claim_event(event.event_id, run["run_id"], asdict(event)):
                return self._current_result(
                    run["run_id"], "Recorded event replayed without another effect."
                )
            if run["stage"] in {
                "awaiting_provider_reply",
                "awaiting_effective_date",
                "completed",
                "provider_review",
                "stopped",
            }:
                raise ValueError(
                    "Case has advanced; changed decisions need a separate amendment/review"
                )
            if event.event_type == "internal_approval":
                if run["internal_event_id"]:
                    raise ValueError(
                        "A different approval requires a new review, not scope replacement"
                    )
                if event.decision == "approved":
                    self._validate_scope(event.approved_scope)
                    current = self.store.db.execute(
                        "SELECT seat_limit FROM software_subscriptions WHERE subscription_id=?",
                        (run["subscription_id"],),
                    ).fetchone()[0]
                    scope = event.approved_scope
                    action = (
                        "expand"
                        if scope["new_seat_limit"] > current
                        else "reduce" if scope["new_seat_limit"] < current else "renew"
                    )
                    if scope["action"] != action:
                        raise ValueError(
                            "Approval action does not match its seat scope"
                        )
                self.store.db.execute(
                    "UPDATE renewal_runs SET internal_event_id=?,internal_decision=?,internal_actor_id=?,approved_scope_json=? WHERE run_id=?",
                    (
                        event.event_id,
                        event.decision,
                        event.actor_employee_id,
                        (
                            json.dumps(event.approved_scope)
                            if event.approved_scope
                            else None
                        ),
                        run["run_id"],
                    ),
                )
            else:
                if (
                    event.event_type == "finance_clearance"
                    and event.approval_id != "AP002"
                ):
                    raise ValueError("Finance clearance must identify AP002")
                self.store.db.execute(
                    "INSERT OR REPLACE INTO renewal_clearances VALUES (?,?,?,?,?,?)",
                    (
                        run["run_id"],
                        event.event_type,
                        event.event_id,
                        event.actor_employee_id,
                        event.decision,
                        event.decided_at,
                    ),
                )
            run = self.store.get_run(run["run_id"])
            if event.decision == "rejected":
                self.store.set_state(
                    run["run_id"],
                    "stopped",
                    "refused",
                    "Internal decision rejected",
                    "Case owner must initiate a new review",
                    event.decided_at,
                )
            elif self._preconditions(run):
                scope = json.loads(run["approved_scope_json"])
                self.provider_email.send(
                    run_id=run["run_id"],
                    recipient="nina.alvarez@webex-vendor.example",
                    subject=f"Approved renewal request {run['contract_id']}",
                    body=f"Contract {run['contract_id']}; approved request: "
                    + json.dumps(scope, sort_keys=True),
                    created_at=event.decided_at,
                )
                self.store.set_state(
                    run["run_id"],
                    "awaiting_provider_reply",
                    "pending",
                    "Scoped approval and both clearances recorded",
                    "Supplier final confirmation required",
                    event.decided_at,
                )
            else:
                self.store.set_state(
                    run["run_id"],
                    "awaiting_internal_approval",
                    "pending",
                    "Approval or clearance still missing",
                    "Obtain scoped IT approval, Finance AP002 resolution and security review",
                    event.decided_at,
                )
            self.store.mark_processed(
                event.event_id, run["run_id"], event.event_type, event.decided_at
            )
            result = self._current_result(
                run["run_id"], self.store.get_run(run["run_id"])["reason"]
            )
            span.update(output=asdict(result))
            return result

    @transaction
    def handle_provider_reply(self, run_id, fixture_id, provider_reply=None):
        run = self.store.get_run(run_id)
        if not run:
            raise ValueError("Unknown renewal run")
        reply = (
            provider_reply
            if provider_reply is not None
            else self.provider_email.fetch_reply(fixture_id)
        )
        message = message_from_string(reply)
        identity = message.get("Message-ID") or fixture_id
        event_id = f"provider:{run_id}:{identity}"
        if not self.store.claim_event(event_id, run_id, {"reply": reply}):
            return self._current_result(
                run_id, "Supplier message replayed without another effect."
            )
        if run["stage"] != "awaiting_provider_reply" or not self._preconditions(run):
            raise PermissionError(
                "All internal preconditions are required before processing supplier agreement"
            )
        try:
            parsed = parsedate_to_datetime(message.get("Date", ""))
            timestamp = parsed.isoformat()
            date_valid = True
        except (ValueError, TypeError):
            timestamp = run["updated_at"]
            date_valid = False
        if timestamp[:10] < run["updated_at"][:10]:
            raise ValueError("Provider confirmation predates internal clearance")
        decision = self.extractor.extract(fixture_id, reply)
        self.store.record_provider_decision(
            run_id, fixture_id, decision.as_dict(), timestamp
        )
        allowed, reason = self._allow_apply(run, decision)
        if not date_valid:
            allowed, reason = False, "Supplier message lacks a valid date"
        if allowed:
            self.store.record_agreement(run_id, decision, timestamp)
            answer = (
                "Confirmed, awaiting effective date "
                + decision.term_start_date
                + ". Current capacity is unchanged."
            )
        else:
            next_party = (
                "Finance and case owner"
                if decision.decision in {"conditional", "ambiguous"}
                else "Case owner"
            )
            self.store.set_state(
                run_id,
                "provider_review",
                "needs_human",
                reason,
                next_party + " must resolve the supplier response",
                timestamp,
            )
            self.notifications.send(
                run_id=run_id,
                idempotency_key=run_id + ":provider-review:" + identity,
                channel="slack",
                recipient=run["approver_id"],
                kind="provider_review_required",
                subject="Supplier reply requires review",
                body=reason + "; next party: " + next_party,
                created_at=timestamp,
            )
            answer = (
                reason + "; " + next_party + " must resolve it. No commercial update."
            )
        self.store.mark_processed(event_id, run_id, "provider_reply", timestamp)
        return self._current_result(run_id, answer, decision=decision)

    def _allow_apply(self, run, decision):
        if (
            decision.decision != "approved"
            or decision.missing_fields
            or decision.conditions
        ):
            return (
                False,
                f"Supplier decision {decision.decision}; missing {decision.missing_fields}; conditions {decision.conditions}",
            )
        if decision.contract_id != run["contract_id"]:
            return False, "Supplier contract mismatch"
        scope = json.loads(run["approved_scope_json"])
        if (
            decision.new_seat_limit != scope["new_seat_limit"]
            or decision.annual_cost_usd > scope["annual_cost_ceiling_usd"]
            or decision.annual_cost_usd <= 0
        ):
            return False, "Supplier price or seats outside approved scope"
        if any(
            getattr(decision, k) != scope[k]
            for k in ("term_start_date", "term_end_date")
        ):
            return False, "Supplier term outside approved scope"
        previous_end = self.store.db.execute(
            "SELECT end_date FROM contracts WHERE contract_id=?", (run["contract_id"],)
        ).fetchone()[0]
        if date.fromisoformat(decision.term_start_date) != date.fromisoformat(
            previous_end
        ) + timedelta(days=1):
            return False, "Term does not follow current agreement"
        if not decision.confirmation_id:
            return False, "No confirmation identifier"
        return True, "Approved scope and clearances match final supplier terms"

    @transaction
    def activate_due(self, as_of):
        date.fromisoformat(as_of)
        results = []
        rows = self.store.db.execute(
            "SELECT a.* FROM renewal_agreements a JOIN renewal_runs r ON r.run_id=a.run_id WHERE a.effective_date<=? AND r.stage IN ('awaiting_effective_date','completed')",
            (as_of,),
        ).fetchall()
        for row in rows:
            if as_of < row["recorded_at"][:10]:
                continue
            run = self.store.get_run(row["run_id"])
            if not self._preconditions(run):
                raise PermissionError("Clearances no longer valid")
            decision = ProviderRenewalDecision(**json.loads(row["decision_json"]))
            timestamp = as_of + "T00:00:00Z"
            with observe(
                "renewal_apply_update", input={"as_of": as_of, "run_id": run["run_id"]}
            ) as span:
                applied = self.store.apply_approved(run["run_id"], decision, timestamp)
                if applied:
                    self._notify_blocked_users(run["run_id"], timestamp)
                    self.store.set_state(
                        run["run_id"],
                        "completed",
                        "completed",
                        "Confirmed terms applied on " + as_of,
                        "Notification intents recorded; inspect delivery status",
                        timestamp,
                    )
                result = self._current_result(
                    run["run_id"],
                    "Confirmed terms are effective; notification intents are queued. Access is unchanged.",
                )
                span.update(output=asdict(result), metadata={"new_update": applied})
                results.append(result)
        return results

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
            if self.store.record_notification(
                run_id, employee["employee_id"], message_id, timestamp
            ):
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
    security_reviewer_id: str | None = None,
) -> RenewalWorkflow:
    store = RenewalStore()
    return RenewalWorkflow(
        store,
        MockNotificationAdapter(store),
        MockProviderEmailAdapter(store, replies=replies),
        extractor or ProviderDecisionExtractor(),
        security_reviewer_id=security_reviewer_id,
    )
