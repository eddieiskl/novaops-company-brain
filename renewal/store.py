from __future__ import annotations

import hashlib
import json
from typing import Any

from maya import ops


class RenewalStore:
    """SQLite persistence and idempotency oracle for the offline workflow."""

    def __init__(self) -> None:
        self.db = ops.conn()

    def due_webex(self, as_of: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT c.*, s.subscription_id, s.seat_limit, s.active_seats, s.annual_cost AS subscription_cost, "
            "s.renewal_date, d.default_manager_id AS approver_id, sys.system_name, v.vendor_name "
            "FROM contracts c JOIN software_subscriptions s ON s.contract_id = c.contract_id "
            "JOIN departments d ON d.department_id = c.owner_department_id "
            "JOIN systems sys ON sys.system_id = c.system_id JOIN vendors v ON v.vendor_id = c.vendor_id "
            "WHERE c.contract_id = 'C001' AND date(?) BETWEEN date(c.end_date, '-90 day') AND date(c.end_date)",
            (as_of,),
        ).fetchone()
        return dict(row) if row else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM renewal_runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def create_run(self, due: dict[str, Any], as_of: str) -> dict[str, Any]:
        run_id = f"RR-WEBEX-{due['end_date'][:4]}"
        notice_deadline = self.db.execute(
            "SELECT date(?, '-' || ? || ' day') AS deadline",
            (due["end_date"], due["renewal_notice_days"]),
        ).fetchone()["deadline"]
        urgent = int(as_of > notice_deadline)
        timestamp = f"{as_of}T00:00:00Z"
        self.db.execute(
            "INSERT OR IGNORE INTO renewal_runs "
            "(run_id, contract_id, subscription_id, approver_id, stage, status, as_of_date, urgent, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'awaiting_internal_approval', 'pending', ?, ?, ?, ?)",
            (run_id, due["contract_id"], due["subscription_id"], due["approver_id"], as_of, urgent, timestamp, timestamp),
        )
        self.db.commit()
        return self.get_run(run_id) or {}

    def enqueue(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        channel: str,
        recipient: str,
        kind: str,
        subject: str,
        body: str,
        created_at: str,
    ) -> str:
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16].upper()
        message_id = f"MSG-{digest}"
        self.db.execute(
            "INSERT OR IGNORE INTO renewal_outbox "
            "(message_id, idempotency_key, run_id, channel, recipient, kind, subject, body, delivery_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
            (message_id, idempotency_key, run_id, channel, recipient, kind, subject, body, created_at),
        )
        self.db.commit()
        row = self.db.execute(
            "SELECT message_id FROM renewal_outbox WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return str(row["message_id"])

    def processed(self, event_id: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM renewal_processed_events WHERE event_id = ?", (event_id,)
        ).fetchone() is not None

    def mark_processed(self, event_id: str, run_id: str, event_type: str, timestamp: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO renewal_processed_events (event_id, run_id, event_type, processed_at) VALUES (?, ?, ?, ?)",
            (event_id, run_id, event_type, timestamp),
        )
        self.db.commit()

    def record_internal_decision(self, event: Any) -> None:
        stage = "awaiting_provider_reply" if event.decision == "approved" else "stopped"
        status = "pending" if event.decision == "approved" else "refused"
        self.db.execute(
            "UPDATE renewal_runs SET stage = ?, status = ?, internal_event_id = ?, internal_decision = ?, "
            "internal_actor_id = ?, updated_at = ? WHERE run_id = ?",
            (stage, status, event.event_id, event.decision, event.actor_employee_id, event.decided_at, event.renewal_run_id),
        )
        self.db.commit()

    def record_provider_decision(self, run_id: str, fixture_id: str, decision: dict[str, Any], timestamp: str) -> None:
        self.db.execute(
            "UPDATE renewal_runs SET provider_fixture_id = ?, provider_decision_json = ?, updated_at = ? WHERE run_id = ?",
            (fixture_id, json.dumps(decision, sort_keys=True), timestamp, run_id),
        )
        self.db.commit()

    def mark_needs_human(self, run_id: str, timestamp: str) -> None:
        self.db.execute(
            "UPDATE renewal_runs SET stage = 'provider_review', status = 'needs_human', updated_at = ? WHERE run_id = ?",
            (timestamp, run_id),
        )
        self.db.commit()

    def apply_approved(self, run_id: str, decision: Any, timestamp: str) -> bool:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown renewal run: {run_id}")
        if self.db.execute("SELECT 1 FROM renewal_applied_updates WHERE run_id = ?", (run_id,)).fetchone():
            return False
        update_id = f"RU-{run_id}"
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "UPDATE contracts SET start_date = ?, end_date = ?, annual_cost = ?, status = 'active' WHERE contract_id = ?",
                (decision.term_start_date, decision.term_end_date, decision.annual_cost_usd, run["contract_id"]),
            )
            self.db.execute(
                "UPDATE software_subscriptions SET seat_limit = ?, annual_cost = ?, renewal_date = ?, status = 'active' "
                "WHERE subscription_id = ?",
                (decision.new_seat_limit, decision.annual_cost_usd, decision.term_end_date, run["subscription_id"]),
            )
            self.db.execute(
                "INSERT INTO renewal_applied_updates "
                "(update_id, run_id, contract_id, subscription_id, confirmation_id, new_seat_limit, annual_cost_usd, "
                "term_start_date, term_end_date, applied_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    update_id,
                    run_id,
                    run["contract_id"],
                    run["subscription_id"],
                    decision.confirmation_id,
                    decision.new_seat_limit,
                    decision.annual_cost_usd,
                    decision.term_start_date,
                    decision.term_end_date,
                    timestamp,
                ),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO audit_log "
                "(event_id, entity_type, entity_id, event_type, actor_employee_id, created_at, notes) "
                "VALUES (?, 'contract', ?, 'renewal_applied', ?, ?, ?)",
                (
                    f"EV-{run_id}-APPLIED",
                    run["contract_id"],
                    run["internal_actor_id"],
                    timestamp,
                    f"Provider confirmation {decision.confirmation_id}; {decision.new_seat_limit} seats; USD {decision.annual_cost_usd}.",
                ),
            )
            self.db.execute(
                "UPDATE renewal_runs SET stage = 'completed', status = 'completed', updated_at = ? WHERE run_id = ?",
                (timestamp, run_id),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return True

    def blocked_employees(self, run_id: str) -> list[dict[str, Any]]:
        run = self.get_run(run_id)
        if run is None:
            return []
        rows = self.db.execute(
            "SELECT DISTINCT e.employee_id, e.full_name, e.email FROM access_requests ar "
            "JOIN employees e ON e.employee_id = ar.employee_id "
            "JOIN software_subscriptions s ON s.system_id = ar.system_id "
            "WHERE s.subscription_id = ? AND ar.status = 'blocked' ORDER BY e.employee_id",
            (run["subscription_id"],),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_notification(self, run_id: str, employee_id: str, message_id: str, timestamp: str) -> bool:
        notification_id = f"RN-{run_id}-{employee_id}"
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO renewal_notifications (notification_id, run_id, employee_id, message_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (notification_id, run_id, employee_id, message_id, timestamp),
        )
        self.db.commit()
        return cursor.rowcount == 1

    def outbox(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM renewal_outbox WHERE run_id = ? ORDER BY created_at, message_id", (run_id,)
        ).fetchall()]

    def notifications(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM renewal_notifications WHERE run_id = ? ORDER BY employee_id", (run_id,)
        ).fetchall()]

    def applied_updates(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM renewal_applied_updates WHERE run_id = ?", (run_id,)
        ).fetchall()]
