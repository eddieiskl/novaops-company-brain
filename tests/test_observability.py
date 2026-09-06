from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain import CompanyBrainAgent
from company_brain.observability import TracedCompanyBrainAgent
from maya import CallerContext, ops


class FakeSpan:
    def __init__(self, record: dict) -> None:
        self.record = record

    def update(self, **kwargs) -> None:
        self.record["update"] = kwargs


class FakeLangfuse:
    def __init__(self) -> None:
        self.observations: list[dict] = []
        self.scores: dict[str, float] = {}
        self.flushed = False

    def auth_check(self) -> bool:
        return True

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        record = dict(kwargs)
        self.observations.append(record)
        yield FakeSpan(record)

    def score_current_trace(self, *, name: str, value: float, **kwargs) -> None:
        self.scores[name] = value

    def get_current_trace_id(self) -> str:
        return "trace-test-001"

    def get_trace_url(self, *, trace_id: str) -> str:
        return f"https://langfuse.example/trace/{trace_id}"

    def flush(self) -> None:
        self.flushed = True


def test_trace_contains_required_decision_and_tool_spans(monkeypatch) -> None:
    ops.reset_conn()
    fake = FakeLangfuse()
    monkeypatch.setattr("company_brain.observability.propagate_attributes", lambda **kwargs: nullcontext())
    traced = TracedCompanyBrainAgent(CompanyBrainAgent(), client=fake)

    result = traced.handle_turn(
        "trace-thread",
        CallerContext("E010", "UG_REGULAR"),
        "Can I use my personal laptop for work?",
        turn=1,
        request_id="M-I-01:single",
        case_id="M-I-01",
    )
    traced.flush()

    names = [item["name"] for item in fake.observations]
    assert names == ["M-I-01 turn 1", "classify", "scope", "execute", "retrieve_evidence", "answer"]
    root = fake.observations[0]
    tool = next(item for item in fake.observations if item["name"] == "retrieve_evidence")
    assert tool["input"]["arguments"]["caller_employee_id"] == "E010"
    assert tool["input"]["arguments"]["required_evidence"] == [
        "equipment_policy.md",
        "acceptable_use_policy.md",
    ]
    assert tool["update"]["metadata"]["completed"] is True
    assert len(tool["update"]["output"]) >= 2
    assert root["update"]["input"]["current_message"] == "Can I use my personal laptop for work?"
    assert root["update"]["input"]["conversation_history"] == []
    assert root["update"]["input"]["grounding_context"]["retrieved_evidence"]
    assert result.trace_id == "trace-test-001"
    assert result.trace_metadata()["request_id"] == "M-I-01:single"
    assert result.trace_metadata()["workflow_scope"] == "maya_hr"
    assert "scope" not in result.trace_metadata()
    assert all(value == 1.0 for value in fake.scores.values())
    assert fake.flushed is True


def test_follow_up_trace_contains_prior_conversation_for_evaluators(monkeypatch) -> None:
    ops.reset_conn()
    fake = FakeLangfuse()
    monkeypatch.setattr("company_brain.observability.propagate_attributes", lambda **kwargs: nullcontext())
    traced = TracedCompanyBrainAgent(CompanyBrainAgent(), client=fake)
    caller = CallerContext("E004", "UG_HR")

    first = traced.handle_turn("history-thread", caller, "Pull up Maya Cohen's employee record.", turn=1)
    traced.handle_turn("history-thread", caller, "What does her offer letter require?", turn=2)

    second_root = [item for item in fake.observations if item.get("as_type") == "agent"][1]
    history = second_root["update"]["input"]["conversation_history"]
    assert history == [
        {"role": "user", "content": "Pull up Maya Cohen's employee record."},
        {"role": "assistant", "content": first.answer},
    ]
