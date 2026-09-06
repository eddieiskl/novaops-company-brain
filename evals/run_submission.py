from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Iterable

import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env", override=False)

from company_brain import build_company_brain_from_env
from company_brain.observability import TracedCompanyBrainAgent
from maya import CallerContext, ops


GROUPS = {
    "HR Group": "UG_HR",
    "IT Group": "UG_IT",
    "Regular Employee": "UG_REGULAR",
}


def load_inputs() -> dict:
    return yaml.safe_load((ROOT / "spec" / "EVALUATION-INPUTS.yaml").read_text(encoding="utf-8"))


def required_workflows(dataset: dict, include_optional: bool = False) -> Iterable[dict]:
    for workflow in dataset["workflows"]:
        if workflow.get("required") or include_optional:
            yield workflow


def caller_context(caller: dict) -> CallerContext:
    try:
        group = GROUPS[caller["group"]]
    except KeyError as exc:
        raise ValueError(f"Unknown evaluation caller group: {caller['group']!r}") from exc
    return CallerContext(caller["employee_id"], group)  # type: ignore[arg-type]


def run(*, trace: bool, include_optional: bool = False) -> dict:
    dataset = load_inputs()
    records: list[dict] = []
    for workflow in required_workflows(dataset, include_optional):
        if not workflow.get("required"):
            # Vendor and Renewal are deliberately separate entry points and are not
            # run until those optional modules are selected for delivery.
            continue
        for case in workflow.get("inputs", []):
            ops.reset_conn()
            agent = TracedCompanyBrainAgent(build_company_brain_from_env(), enabled=trace, require_auth=trace)
            caller = caller_context(case["caller"])
            request_id = f"{case['id']}:single"
            result = agent.handle_turn(
                case["id"],
                caller,
                case["message"],
                turn=1,
                request_id=request_id,
                case_id=case["id"],
            )
            records.append(_record(case["id"], None, result))
            agent.flush()

        for session in workflow.get("sessions", []):
            ops.reset_conn()
            agent = TracedCompanyBrainAgent(build_company_brain_from_env(), enabled=trace, require_auth=trace)
            caller = caller_context(session["caller"])
            for turn in session["turns"]:
                request_id = f"{session['id']}:turn:{turn['n']}"
                result = agent.handle_turn(
                    session["id"],
                    caller,
                    turn["message"],
                    turn=turn["n"],
                    request_id=request_id,
                    case_id=session["id"],
                )
                records.append(_record(session["id"], turn["n"], result))
            agent.flush()

    expected = 27
    summary = {
        "mode": "trace" if trace else "dry-run",
        "expected_required_traces": expected,
        "produced": len(records),
        "all_deterministic_checks_pass": all(
            all(value == 1.0 for value in record["scores"].values()) for record in records
        ),
        "trace_ids_present": sum(bool(record["trace_id"]) for record in records),
    }
    return {"summary": summary, "records": records}


def _record(item_id: str, turn: int | None, result) -> dict:
    return {
        "item": item_id,
        "turn": turn,
        "request_id": result.request_id,
        "trace_id": result.trace_id,
        "trace_url": result.trace_url,
        "scope": result.scope,
        "intent": result.intent,
        "status": result.status,
        "tool_sequence": result.tool_sequence,
        "citations": result.citations,
        "scores": result.scores,
        "answer": result.answer,
    }


def update_submission(records: list[dict], path: Path) -> None:
    if any(not record["trace_id"] for record in records):
        raise ValueError("Cannot update SUBMISSION.md until every required record has a Langfuse trace id.")
    queues: dict[tuple[str, str], list[str]] = {}
    for record in records:
        turn = "—" if record["turn"] is None else str(record["turn"])
        queues.setdefault((record["item"], turn), []).append(record["trace_id"])

    pattern = re.compile(r"^(\| `(?P<item>[^`]+)` \| (?P<turn>[^|]+?) \|)\s*[^|]*\|$")
    output: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            key = (match.group("item"), match.group("turn").strip())
            trace_ids = queues.get(key)
            if trace_ids:
                line = f"{match.group(1)} {trace_ids.pop(0)} |"
        output.append(line)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NovaOps final-project submission inputs.")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Write the official one-trace-per-turn run to Langfuse. Omit for a local dry-run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".state" / "submission-evaluation.json",
        help="Where to write the local trace index and outputs.",
    )
    parser.add_argument(
        "--update-submission",
        action="store_true",
        help="Fill only the trace-id cells in SUBMISSION.md after a successful traced run.",
    )
    args = parser.parse_args()
    try:
        result = run(trace=args.trace)
    except RuntimeError as exc:
        print(f"evaluation aborted: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.update_submission:
        update_submission(result["records"], ROOT / "SUBMISSION.md")
    print(json.dumps(result["summary"], indent=2))
    print(f"results: {args.output}")
    return 0 if result["summary"]["all_deterministic_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
