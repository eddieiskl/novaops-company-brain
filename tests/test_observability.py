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
    assert names == ["M-I-01 turn 1", "classify", "scope", "search_evidence", "answer"]
    assert result.trace_id == "trace-test-001"
    assert result.trace_metadata()["request_id"] == "M-I-01:single"
    assert all(value == 1.0 for value in fake.scores.values())
    assert fake.flushed is True
