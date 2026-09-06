from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from binding_checks import load_binding_expectations, score_binding_expectation
from run_submission import load_inputs, required_workflows, run, update_submission


def test_submission_manifest_contains_27_required_turns() -> None:
    count = 0
    for workflow in required_workflows(load_inputs()):
        count += len(workflow.get("inputs", []))
        count += sum(len(session["turns"]) for session in workflow.get("sessions", []))
    assert count == 27
    assert len(load_binding_expectations(load_inputs())) == 27


def test_required_submission_dry_run_has_complete_local_trace_index() -> None:
    result = run(trace=False)

    assert result["summary"]["produced"] == 27
    assert result["summary"]["trace_ids_present"] == 0
    assert result["summary"]["all_deterministic_checks_pass"] is True
    assert result["summary"]["all_binding_checks_pass"] is True
    assert result["summary"]["unmapped_required_inputs"] == []
    assert {(row["item"], row["turn"]) for row in result["records"]} >= {
        ("M-I-01", None),
        ("M-S-01", 12),
        ("M-S-02", 5),
        ("W-I-03", None),
        ("W-S-01", 4),
    }


def test_optional_submission_dry_run_produces_all_33_records() -> None:
    result = run(trace=False, include_optional=True)

    assert result["summary"]["produced"] == 33
    assert result["summary"]["expected_required_traces"] == 33
    assert result["summary"]["all_deterministic_checks_pass"] is True
    assert {(row["item"], row["status"]) for row in result["records"]} >= {
        ("V-I-01", "completed"),
        ("R-I-01", "completed"),
        ("R-I-02", "needs_human"),
        ("R-I-03", "needs_human"),
    }


def test_trace_index_writer_only_fills_matching_submission_cells(tmp_path) -> None:
    submission = tmp_path / "SUBMISSION.md"
    submission.write_text(
        "| Item | Turn | Trace ID |\n"
        "| --- | --- | --- |\n"
        "| `M-I-01` | — | |\n"
        "| `M-S-01` | 1 | |\n",
        encoding="utf-8",
    )
    records = [
        {"item": "M-I-01", "turn": None, "trace_id": "trace-a"},
        {"item": "M-S-01", "turn": 1, "trace_id": "trace-b"},
    ]

    update_submission(records, submission)

    text = submission.read_text(encoding="utf-8")
    assert "| `M-I-01` | — | trace-a |" in text
    assert "| `M-S-01` | 1 | trace-b |" in text


def test_binding_scorer_reports_missing_required_fact_and_forbidden_source() -> None:
    class Result:
        answer = "The answer omits the expected identifier."
        tool_sequence = []
        citations = ["documents/manager_playbook/promotion.md"]
        payload = None

    scores, comments = score_binding_expectation(
        Result(),
        {
            "required_facts": ["E001"],
            "forbidden_sources": ["manager_playbook/promotion.md"],
            "should_use_tools": True,
        },
    )

    assert scores == {
        "binding_required_facts": 0.0,
        "binding_forbidden_sources": 0.0,
        "binding_tool_use": 0.0,
    }
    assert "E001" in comments["binding_required_facts"]
