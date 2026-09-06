from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from run_submission import load_inputs, required_workflows, run, update_submission


def test_submission_manifest_contains_27_required_turns() -> None:
    count = 0
    for workflow in required_workflows(load_inputs()):
        count += len(workflow.get("inputs", []))
        count += sum(len(session["turns"]) for session in workflow.get("sessions", []))
    assert count == 27


def test_required_submission_dry_run_has_complete_local_trace_index() -> None:
    result = run(trace=False)

    assert result["summary"]["produced"] == 27
    assert result["summary"]["trace_ids_present"] == 0
    assert result["summary"]["all_deterministic_checks_pass"] is True
    assert {(row["item"], row["turn"]) for row in result["records"]} >= {
        ("M-I-01", None),
        ("M-S-01", 12),
        ("M-S-02", 5),
        ("W-I-03", None),
        ("W-S-01", 4),
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
