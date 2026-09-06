from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


TerminalStatus = Literal["completed", "blocked", "pending", "needs_human", "failed"]


@dataclass
class AgentTurnResult:
    request_id: str
    thread_id: str
    turn: int
    scope: Literal["maya_hr", "webex_ops"]
    intent: str
    status: TerminalStatus
    answer: str
    caller_employee_id: str
    caller_user_group: str
    tool_sequence: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    payload: Any = None
    trace_id: str | None = None
    trace_url: str | None = None
    scores: dict[str, float] = field(default_factory=dict)

    def trace_metadata(self) -> dict:
        return {
            "request_id": self.request_id,
            "thread_id": self.thread_id,
            "turn": self.turn,
            "caller_id": self.caller_employee_id,
            "caller_group": self.caller_user_group,
            "scope": self.scope,
            "intent": self.intent,
            "tool_sequence": self.tool_sequence,
            "status": self.status,
        }
