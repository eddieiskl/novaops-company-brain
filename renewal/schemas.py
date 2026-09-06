from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class InternalApprovalEvent:
    event_id: str
    renewal_run_id: str
    contract_id: str
    actor_employee_id: str
    decision: Literal["approved", "rejected"]
    channel: str
    reason: str
    decided_at: str


@dataclass
class RenewalResult:
    run_id: str
    status: Literal["pending", "completed", "needs_human", "refused", "failed"]
    stage: str
    answer: str
    applied: bool = False
    subscription_updated: bool = False
    notified_employee_ids: list[str] = field(default_factory=list)
    outbox_message_ids: list[str] = field(default_factory=list)
    provider_decision: Any = None
    trace_id: str | None = None
    trace_url: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    score_comments: dict[str, str] = field(default_factory=dict)
