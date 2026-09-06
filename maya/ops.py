from __future__ import annotations

import functools
import hashlib
import os
import sqlite3
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "novaops-enterprise-agent-dataset"
DEFAULT_DB_PATH = PROJECT_ROOT / ".state" / "novaops.sqlite3"
_thread_local = threading.local()


@functools.lru_cache(maxsize=1)
def _schema_seed() -> tuple[str, str]:
    return (
        (DATA_ROOT / "database" / "schema.sql").read_text(encoding="utf-8"),
        (DATA_ROOT / "database" / "seed.sql").read_text(encoding="utf-8"),
    )


def database_path() -> Path:
    configured = os.getenv("NOVAOPS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH


def _initialize(db: sqlite3.Connection) -> None:
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'employees'"
    ).fetchone()
    if exists is None:
        schema, seed = _schema_seed()
        db.executescript(schema)
        db.executescript(seed)
        db.commit()
    _migrate(db)


def _migrate(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow_handoffs (
            handoff_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            conversation_id TEXT NOT NULL,
            subject_employee_id TEXT NOT NULL,
            software TEXT NOT NULL,
            business_justification TEXT NOT NULL,
            caller_employee_id TEXT NOT NULL,
            status TEXT NOT NULL,
            approval_id TEXT NOT NULL UNIQUE,
            access_request_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS idempotency_records (
            idempotency_key TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS renewal_runs (
            run_id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            subscription_id TEXT NOT NULL,
            approver_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            urgent INTEGER NOT NULL,
            internal_event_id TEXT,
            internal_decision TEXT,
            internal_actor_id TEXT,
            provider_fixture_id TEXT,
            provider_decision_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS renewal_outbox (
            message_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            run_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            recipient TEXT NOT NULL,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            delivery_status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS renewal_processed_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS renewal_applied_updates (
            update_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            contract_id TEXT NOT NULL,
            subscription_id TEXT NOT NULL,
            confirmation_id TEXT NOT NULL,
            new_seat_limit INTEGER NOT NULL,
            annual_cost_usd INTEGER NOT NULL,
            term_start_date TEXT NOT NULL,
            term_end_date TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS renewal_notifications (
            notification_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(run_id, employee_id)
        );
        """
    )
    db.commit()


def conn() -> sqlite3.Connection:
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        return cached

    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    _initialize(db)
    _thread_local.conn = db
    return db


def reset_conn(*, reseed: bool = True) -> None:
    cached = getattr(_thread_local, "conn", None)
    if cached is not None:
        cached.close()
    _thread_local.conn = None
    if reseed:
        path = database_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        try:
            schema, seed = _schema_seed()
            db.executescript(
                "DROP TABLE IF EXISTS renewal_notifications; "
                "DROP TABLE IF EXISTS renewal_applied_updates; "
                "DROP TABLE IF EXISTS renewal_processed_events; "
                "DROP TABLE IF EXISTS renewal_outbox; "
                "DROP TABLE IF EXISTS renewal_runs; "
                "DROP TABLE IF EXISTS workflow_handoffs; "
                "DROP TABLE IF EXISTS idempotency_records;"
            )
            db.executescript(schema)
            db.executescript(seed)
            _migrate(db)
            db.commit()
        finally:
            db.close()


def get_employee(query: str) -> list[dict]:
    like = f"%{query}%"
    rows = conn().execute(
        "SELECT employee_id, full_name, email, role, department_id, manager_id, location, "
        "employment_type, status, start_date, user_group_id, systems_allowed_by_role "
        "FROM employees WHERE employee_id = ? OR lower(email) = lower(?) OR lower(full_name) LIKE lower(?)",
        (query, query, like),
    ).fetchall()
    return [dict(row) for row in rows]


def is_manager(employee_id: str) -> bool:
    row = conn().execute(
        "SELECT 1 FROM employees WHERE manager_id = ? LIMIT 1",
        (employee_id,),
    ).fetchone()
    return row is not None


def list_direct_reports(manager_id: str) -> list[dict]:
    rows = conn().execute(
        "SELECT employee_id, full_name, email, role, department_id, location, status, "
        "systems_allowed_by_role FROM employees WHERE manager_id = ? ORDER BY full_name",
        (manager_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_onboarding_tasks(employee_id: str) -> list[dict]:
    rows = conn().execute(
        "SELECT task_id, task_type, description, owner_group, status, due_date, related_system_id "
        "FROM onboarding_tasks WHERE employee_id = ? ORDER BY due_date, task_id",
        (employee_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def check_asset_inventory(asset_type: str = "", location: str = "") -> list[dict]:
    rows = conn().execute(
        "SELECT asset_id, employee_id, asset_type, model, status, location, notes FROM assets "
        "WHERE lower(asset_type) LIKE lower(?) AND lower(location) LIKE lower(?) ORDER BY asset_id",
        (f"%{asset_type}%", f"%{location}%"),
    ).fetchall()
    return [dict(row) for row in rows]


def list_employee_tickets(employee_id: str, status: str = "") -> list[dict]:
    rows = conn().execute(
        "SELECT ticket_id, category, subcategory, priority, status, subject, created_at, assigned_team "
        "FROM tickets WHERE employee_id = ? AND lower(status) LIKE lower(?) ORDER BY created_at DESC",
        (employee_id, f"%{status}%"),
    ).fetchall()
    return [dict(row) for row in rows]


def list_access_requests(employee_id: str, software: str = "") -> list[dict]:
    rows = conn().execute(
        "SELECT ar.request_id, ar.employee_id, sys.system_name, ar.access_level, "
        "ar.business_justification, ar.status, ar.approver_id, ar.created_at, ar.decision_reason "
        "FROM access_requests ar "
        "JOIN systems sys ON ar.system_id = sys.system_id "
        "WHERE ar.employee_id = ? AND lower(sys.system_name) LIKE lower(?) "
        "ORDER BY ar.created_at DESC",
        (employee_id, f"%{software}%"),
    ).fetchall()
    return [dict(row) for row in rows]


def list_approvals(request_id: str) -> list[dict]:
    rows = conn().execute(
        "SELECT approval_id, request_type, request_id, approver_id, status, decision_reason, created_at "
        "FROM approvals WHERE request_id = ? ORDER BY created_at, approval_id",
        (request_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def inspect_software_seat_assignments(software: str, manager_id: str = "") -> dict:
    """Report the dataset's seat-assignment observability boundary truthfully.

    NovaOps stores aggregate subscription counts, role eligibility, requests and
    onboarding tasks. It does not store an employee-to-seat assignment table.
    Returning that absence as data prevents callers from mistaking entitlement for
    an observed license assignment.
    """
    subscriptions = check_software_subscription(software)
    direct_reports = list_direct_reports(manager_id) if manager_id else []
    report_ids = [employee["employee_id"] for employee in direct_reports]
    requests: list[dict] = []
    tasks: list[dict] = []
    for employee_id in report_ids:
        requests.extend(list_access_requests(employee_id, software))
        employee_tasks = list_onboarding_tasks(employee_id)
        tasks.extend(
            task
            for task in employee_tasks
            if software.lower() in task["description"].lower()
        )
    return {
        "software": software,
        "assignments_recorded": False,
        "authoritative_assignment_source": None,
        "limitation": (
            "The NovaOps dataset records aggregate active-seat counts but has no "
            "employee-to-seat assignment table. Role entitlement is not proof of assignment."
        ),
        "subscription": subscriptions[0] if subscriptions else None,
        "direct_reports": direct_reports,
        "related_access_requests": requests,
        "related_onboarding_tasks": tasks,
    }


def prepare_access_handoff(
    *,
    conversation_id: str,
    subject_employee_id: str,
    software: str,
    business_justification: str,
    caller_employee_id: str,
    idempotency_key: str,
) -> dict:
    """Persist one approval-backed intent without creating an access request."""
    db = conn()
    existing = db.execute(
        "SELECT * FROM workflow_handoffs WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing is not None:
        return dict(existing)

    employee = db.execute(
        "SELECT manager_id FROM employees WHERE employee_id = ?",
        (subject_employee_id,),
    ).fetchone()
    if employee is None:
        raise ValueError(f"Unknown employee_id: {subject_employee_id}")
    if not employee["manager_id"]:
        raise ValueError(f"Employee {subject_employee_id} has no recorded manager approver.")
    system = db.execute(
        "SELECT system_id FROM systems WHERE lower(system_name) = lower(?)",
        (software,),
    ).fetchone()
    if system is None:
        raise ValueError(f"Unknown software: {software}")

    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12].upper()
    handoff_id = f"HO-{digest}"
    approval_id = f"AP-H-{digest}"
    timestamp = f"{os.getenv('NOVAOPS_AS_OF', '2026-07-01')}T12:00:00Z"
    db.execute(
        "INSERT INTO workflow_handoffs "
        "(handoff_id, idempotency_key, conversation_id, subject_employee_id, software, "
        "business_justification, caller_employee_id, status, approval_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?, ?)",
        (
            handoff_id,
            idempotency_key,
            conversation_id,
            subject_employee_id,
            software,
            business_justification,
            caller_employee_id,
            approval_id,
            timestamp,
            timestamp,
        ),
    )
    db.execute(
        "INSERT INTO approvals "
        "(approval_id, request_type, request_id, approver_id, status, decision_reason, created_at) "
        "VALUES (?, 'access_request_intent', ?, ?, 'needed', ?, ?)",
        (
            approval_id,
            handoff_id,
            employee["manager_id"],
            "Manager approval required for standard role-based access.",
            timestamp,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM workflow_handoffs WHERE handoff_id = ?", (handoff_id,)).fetchone())


def get_access_handoff(handoff_id: str) -> dict | None:
    row = conn().execute(
        "SELECT * FROM workflow_handoffs WHERE handoff_id = ?",
        (handoff_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def create_access_request_from_approved_handoff(handoff_id: str) -> dict:
    """Application-only write released after the caller checks the write gate."""
    db = conn()
    handoff = db.execute(
        "SELECT * FROM workflow_handoffs WHERE handoff_id = ?",
        (handoff_id,),
    ).fetchone()
    if handoff is None:
        raise ValueError(f"Unknown handoff_id: {handoff_id}")
    if handoff["access_request_id"]:
        return dict(db.execute(
            "SELECT * FROM access_requests WHERE request_id = ?",
            (handoff["access_request_id"],),
        ).fetchone())

    system = db.execute(
        "SELECT system_id FROM systems WHERE lower(system_name) = lower(?)",
        (handoff["software"],),
    ).fetchone()
    existing = db.execute(
        "SELECT * FROM access_requests WHERE employee_id = ? AND system_id = ? ORDER BY created_at DESC LIMIT 1",
        (handoff["subject_employee_id"], system["system_id"]),
    ).fetchone()
    if existing is not None:
        request_id = existing["request_id"]
    else:
        numeric_ids = [
            int(row["request_id"][2:])
            for row in db.execute("SELECT request_id FROM access_requests").fetchall()
            if row["request_id"].startswith("AR") and row["request_id"][2:].isdigit()
        ]
        request_id = f"AR{max(numeric_ids, default=0) + 1:03d}"
        subscription = check_software_subscription(handoff["software"])
        status = "blocked" if subscription and subscription[0]["over_limit"] else "pending_assignment"
        reason = (
            "Eligible by role and manager-approved, but seats exceed contract limit."
            if status == "blocked"
            else "Manager-approved; pending IT assignment."
        )
        timestamp = f"{os.getenv('NOVAOPS_AS_OF', '2026-07-01')}T12:05:00Z"
        db.execute(
            "INSERT INTO access_requests "
            "(request_id, employee_id, system_id, access_level, business_justification, status, "
            "approver_id, created_at, decision_reason) VALUES (?, ?, ?, 'standard_user', ?, ?, ?, ?, ?)",
            (
                request_id,
                handoff["subject_employee_id"],
                system["system_id"],
                handoff["business_justification"],
                status,
                db.execute("SELECT approver_id FROM approvals WHERE approval_id = ?", (handoff["approval_id"],)).fetchone()["approver_id"],
                timestamp,
                reason,
            ),
        )
        audit_id = f"EV-{handoff_id}-ACCESS-CREATED"
        db.execute(
            "INSERT OR IGNORE INTO audit_log "
            "(event_id, entity_type, entity_id, event_type, actor_employee_id, created_at, notes) "
            "VALUES (?, 'access_request', ?, 'created_from_approved_handoff', ?, ?, ?)",
            (audit_id, request_id, handoff["caller_employee_id"], timestamp, reason),
        )

    db.execute(
        "UPDATE workflow_handoffs SET status = 'released', access_request_id = ?, updated_at = ? WHERE handoff_id = ?",
        (request_id, f"{os.getenv('NOVAOPS_AS_OF', '2026-07-01')}T12:05:00Z", handoff_id),
    )
    db.execute(
        "INSERT OR IGNORE INTO idempotency_records (idempotency_key, operation, entity_id, created_at) "
        "VALUES (?, 'create_access_request', ?, ?)",
        (handoff["idempotency_key"], request_id, f"{os.getenv('NOVAOPS_AS_OF', '2026-07-01')}T12:05:00Z"),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM access_requests WHERE request_id = ?", (request_id,)).fetchone())


def record_approval_decision(
    approval_id: str,
    status: str,
    actor_employee_id: str,
    reason: str,
) -> dict:
    db = conn()
    row = db.execute(
        "SELECT approval_id, request_type, request_id, approver_id, status, decision_reason, created_at "
        "FROM approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown approval_id: {approval_id}")
    if status not in {"approved", "rejected"}:
        raise ValueError("Approval status must be 'approved' or 'rejected'.")
    if row["approver_id"] != actor_employee_id:
        raise PermissionError(
            f"Approval {approval_id} is assigned to {row['approver_id']}; "
            f"actor {actor_employee_id} cannot decide it."
        )
    db.execute(
        "UPDATE approvals SET status = ?, decision_reason = ? WHERE approval_id = ?",
        (status, reason, approval_id),
    )
    event_id = f"EV-WEBEX-{approval_id}-{status}".upper()
    db.execute(
        "INSERT OR REPLACE INTO audit_log "
        "(event_id, entity_type, entity_id, event_type, actor_employee_id, created_at, notes) "
        "VALUES (?, 'approval', ?, 'approval_decision', ?, '2026-08-19T00:00:00Z', ?)",
        (event_id, approval_id, actor_employee_id, reason),
    )
    db.commit()
    return dict(db.execute(
        "SELECT approval_id, request_type, request_id, approver_id, status, decision_reason, created_at "
        "FROM approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone())


def check_software_subscription(software: str) -> list[dict]:
    rows = conn().execute(
        "SELECT sys.system_name, v.vendor_name, sub.seat_limit, sub.active_seats, sub.status, "
        "sub.renewal_date, sub.annual_cost FROM software_subscriptions sub "
        "JOIN systems sys ON sub.system_id = sys.system_id "
        "JOIN vendors v ON sub.vendor_id = v.vendor_id "
        "WHERE lower(sys.system_name) LIKE lower(?) OR lower(v.vendor_name) LIKE lower(?)",
        (f"%{software}%", f"%{software}%"),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["seats_available"] = item["seat_limit"] - item["active_seats"]
        item["over_limit"] = item["active_seats"] >= item["seat_limit"]
        result.append(item)
    return result
