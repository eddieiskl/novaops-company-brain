from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


UserGroup = Literal["UG_HR", "UG_IT", "UG_REGULAR"]


@dataclass(frozen=True)
class CallerContext:
    employee_id: str
    user_group: UserGroup


@dataclass(frozen=True)
class EvidenceCitation:
    source_path: str
    chunk_id: str
    collection: str
    title: str


@dataclass(frozen=True)
class EvidenceChunk:
    source_path: str
    chunk_id: str
    collection: str
    title: str
    text: str
    audience: str
    sensitivity: str
    subject_employee_id: str | None = None
    update_date: str | None = None
    score: float = 0.0

    def citation(self) -> EvidenceCitation:
        return EvidenceCitation(
            source_path=self.source_path,
            chunk_id=self.chunk_id,
            collection=self.collection,
            title=self.title,
        )


@dataclass(frozen=True)
class ContextPlan:
    turn: int
    intent: str
    subject_employee_id: str = "E001"
    active_constraints: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    operational_reads: tuple[str, ...] = ()
    allow_webex_handoff: bool = False
    close_tangent: bool = False


@dataclass(frozen=True)
class ChecklistItem:
    name: str
    status: str
    detail: str
    evidence: tuple[EvidenceCitation, ...] = ()


@dataclass(frozen=True)
class WebexHandoff:
    employee_id: str
    software: str
    caller_employee_id: str
    caller_user_group: str
    business_reason: str
    idempotency_key: str
    evidence: tuple[EvidenceCitation, ...] = ()


@dataclass(frozen=True)
class PendingAccessResult:
    request_id: str
    status: str
    idempotency_key: str


@dataclass
class OnboardingChecklist:
    employee_id: str = "E001"
    employee_name: str = "Maya Cohen"
    role: str = "Customer Success Manager"
    start_date: str = "2026-08-01"
    location: str = "Israel"
    systems: list[ChecklistItem] = field(default_factory=list)
    equipment: list[ChecklistItem] = field(default_factory=list)
    policy_requirements: list[ChecklistItem] = field(default_factory=list)
    blocked_items: list[ChecklistItem] = field(default_factory=list)
    handoffs: list[PendingAccessResult] = field(default_factory=list)

    def all_citations(self) -> list[EvidenceCitation]:
        citations: list[EvidenceCitation] = []
        for group in (
            self.systems,
            self.equipment,
            self.policy_requirements,
            self.blocked_items,
        ):
            for item in group:
                citations.extend(item.evidence)
        return citations


@dataclass
class TurnResult:
    turn: int
    intent: str
    answer: str
    checklist: OnboardingChecklist
    retrieved: list[EvidenceChunk] = field(default_factory=list)
    operational_tool_calls: list[str] = field(default_factory=list)
    handoffs: list[PendingAccessResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
