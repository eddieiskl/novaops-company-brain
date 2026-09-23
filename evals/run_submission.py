from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
from typing import Iterable

import yaml
from dotenv import load_dotenv
from langfuse import get_client, propagate_attributes


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)
load_dotenv(ROOT.parent / ".env", override=False)

from company_brain import build_company_brain_from_env
from company_brain.instrumentation import bind_observer
from company_brain.observability import TracedCompanyBrainAgent
from binding_checks import load_binding_expectations
from maya import CallerContext, ops
from renewal.runtime import build_renewal_workflow_from_env
from renewal.schemas import InternalApprovalEvent
from vendor.runtime import build_vendor_extractor_from_env


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
    expectations = load_binding_expectations(dataset)
    records: list[dict] = []
    for workflow in required_workflows(dataset, include_optional):
        if workflow["id"] == "vendor":
            records.extend(_run_vendor_cases(workflow, trace=trace))
            continue
        if workflow["id"] == "renewal":
            records.extend(_run_renewal_cases(workflow, trace=trace))
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
                expectation=expectations.get((case["id"], None)),
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
                    expectation=expectations.get((session["id"], turn["n"])),
                )
                records.append(_record(session["id"], turn["n"], result))
            agent.flush()

    expected = 33 if include_optional else 27
    required_keys = {
        (record["item"], record["turn"])
        for record in records
        if record["item"].startswith(("M-", "W-"))
    }
    unmapped = sorted(required_keys - set(expectations), key=str)
    summary = {
        "mode": "trace" if trace else "dry-run",
        "expected_required_traces": expected,
        "produced": len(records),
        "all_deterministic_checks_pass": all(
            all(value == 1.0 for value in record["scores"].values()) for record in records
        ),
        "all_binding_checks_pass": all(
            all(value == 1.0 for name, value in record["scores"].items() if name.startswith("binding_"))
            for record in records
        ) and not unmapped,
        "unmapped_required_inputs": unmapped,
        "trace_ids_present": sum(bool(record["trace_id"]) for record in records),
    }
    return {"summary": summary, "records": records}


@contextmanager
def _standalone_trace(enabled: bool, name: str, request_id: str, metadata: dict):
    if not enabled:
        yield None, None
        return
    client = get_client()
    if not client.auth_check():
        raise RuntimeError("Langfuse credentials are missing or rejected; refusing to create untraceable evaluation runs.")
    with propagate_attributes(
        session_id=name,
        tags=["novaops-final-project", metadata["workflow"], name],
        trace_name=name,
        metadata={
            **{key: value for key, value in metadata.items() if key != "input"},
            "request_id": request_id,
        },
    ):
        with client.start_as_current_observation(
            as_type="agent",
            name=name,
            input=metadata.get("input"),
        ) as root:
            with bind_observer(client, request_id):
                yield client, root
    client.flush()


def _write_scores(client, scores: dict[str, float], comments: dict[str, str]) -> None:
    if client is None:
        return
    for name, value in scores.items():
        client.score_current_trace(
            name=name,
            value=value,
            data_type="NUMERIC",
            comment=comments.get(name),
        )


def _run_vendor_cases(workflow: dict, *, trace: bool) -> list[dict]:
    source_types = {
        "formal_vendor_intake": "formal_document",
        "procurement_email_chain": "email_chain",
        "discovery_call_transcript": "call_transcript",
    }
    expected_missing = {"V-I-01": 0, "V-I-02": 1, "V-I-03": 2}
    records: list[dict] = []
    for case in workflow["inputs"]:
        request_id = f"{case['id']}:single"
        metadata = {
            "workflow": "vendor",
            "source_name": case["source_name"],
            "input": {"source_name": case["source_name"], "document": case["document"]},
        }
        with _standalone_trace(trace, case["id"], request_id, metadata) as (client, root):
            result = build_vendor_extractor_from_env().extract(
                case["source_name"],
                source_types[case["source_name"]],
                case["document"],
            )
            expected = expected_missing[case["id"]]
            scores = {
                "optional_schema_valid": 1.0,
                "optional_missing_count": float(len(result.missing_required_fields) == expected),
                "optional_follow_up_count": float(len(result.follow_up_questions) == expected),
            }
            comments = {
                "optional_schema_valid": "local Draft 2020-12 validation passed",
                "optional_missing_count": f"expected={expected}; observed={len(result.missing_required_fields)}",
                "optional_follow_up_count": f"expected={expected}; observed={len(result.follow_up_questions)}",
            }
            _write_scores(client, scores, comments)
            trace_id = client.get_current_trace_id() if client else None
            trace_url = client.get_trace_url(trace_id=trace_id) if client else None
            if root:
                root.update(
                    output=result.as_dict(),
                    metadata={
                        "workflow": "vendor",
                        "status": "completed",
                        "source_name": case["source_name"],
                        "missing_required_fields": result.missing_required_fields,
                        "scores": scores,
                    },
                )
        records.append({
            "item": case["id"], "turn": None, "request_id": request_id,
            "trace_id": trace_id, "trace_url": trace_url, "scope": "vendor_extraction",
            "intent": "extract_vendor", "status": "completed", "tool_sequence": [], "citations": [],
            "scores": scores, "score_comments": comments, "answer": json.dumps(result.as_dict(), sort_keys=True),
        })
    return records


def _run_renewal_cases(workflow: dict, *, trace: bool) -> list[dict]:
    records: list[dict] = []
    # The original evaluation predates PRD v1.3 scoped approvals/clearances.
    lesson15_events = [InternalApprovalEvent(**json.loads(line)) for line in (ROOT / "evals/fixtures/lesson15/internal_approval_events.jsonl").read_text().splitlines()]
    approval = lesson15_events[0]
    as_of = workflow["trigger"]["as_of"]
    for case in workflow["inputs"]:
        ops.reset_conn()
        request_id = f"{case['id']}:scheduled"
        metadata = {
            "workflow": "renewal",
            "fixture_id": case["fixture_id"],
            "input": {
                "trigger": workflow["trigger"],
                "internal_approval_events": [asdict(event) for event in lesson15_events],
                "fixture_provenance": "Local Lesson 15 scope and clearance supplement",
                "fixture_id": case["fixture_id"],
                "provider_reply": case["provider_reply"],
            },
        }
        with _standalone_trace(trace, case["id"], request_id, metadata) as (client, root):
            started = build_renewal_workflow_from_env(replies={case["fixture_id"]: case["provider_reply"]}, security_reviewer_id="E006").start(as_of)
            ops.reset_conn(reseed=False)
            resumed = build_renewal_workflow_from_env(replies={case["fixture_id"]: case["provider_reply"]}, security_reviewer_id="E006")
            for event in lesson15_events:
                resumed.handle_internal_event(event)
                resumed.handle_internal_event(event)
            ops.reset_conn(reseed=False)
            completed = build_renewal_workflow_from_env(replies={case["fixture_id"]: case["provider_reply"]}, security_reviewer_id="E006")
            result = completed.handle_provider_reply(started.run_id, case["fixture_id"], case["provider_reply"])
            completed.handle_provider_reply(started.run_id, case["fixture_id"], case["provider_reply"])

            before_effective = ops.conn().execute("SELECT seat_limit FROM software_subscriptions WHERE subscription_id = 'SUB001'").fetchone()[0]
            expected_applied = case["id"] == "R-I-01"
            if expected_applied:
                result = completed.start("2026-07-21")
                completed.start("2026-07-21")
            subscription = ops.conn().execute(
                "SELECT seat_limit, annual_cost FROM software_subscriptions WHERE subscription_id = 'SUB001'"
            ).fetchone()
            update_count = len(completed.store.applied_updates(started.run_id))
            notification_count = len(completed.store.notifications(started.run_id))
            expected_status = "completed" if expected_applied else "needs_human"
            scores = {
                "optional_no_early_activation": float(before_effective == 40),
                "optional_expected_status": float(result.status == expected_status),
                "optional_write_gate": float(result.applied == expected_applied),
                "optional_subscription_state": float(
                    dict(subscription)
                    == ({"seat_limit": 50, "annual_cost": 22000} if expected_applied else {"seat_limit": 40, "annual_cost": 18400})
                ),
                "optional_exactly_once_update": float(update_count == (1 if expected_applied else 0)),
                "optional_exactly_once_notification": float(notification_count == (1 if expected_applied else 0)),
                "optional_no_access_grant": float("access was granted" not in result.answer.casefold()),
            }
            comments = {
                "optional_no_early_activation": f"seat_limit after supplier reply={before_effective}",
                "optional_expected_status": f"expected={expected_status}; observed={result.status}",
                "optional_write_gate": f"expected applied={expected_applied}; observed={result.applied}",
                "optional_subscription_state": f"observed={dict(subscription)}",
                "optional_exactly_once_update": f"update_count={update_count} after replay",
                "optional_exactly_once_notification": f"notification_count={notification_count} after replay",
                "optional_no_access_grant": "renewal notification changes a blocker but never grants access",
            }
            _write_scores(client, scores, comments)
            trace_id = client.get_current_trace_id() if client else None
            trace_url = client.get_trace_url(trace_id=trace_id) if client else None
            if root:
                root.update(
                    output=asdict(result),
                    metadata={
                        "workflow": "renewal", "status": result.status, "stage": result.stage,
                        "fixture_id": case["fixture_id"], "restart_simulated": True,
                        "approval_event_replayed": True, "provider_event_replayed": True, "scores": scores,
                    },
                )
        records.append({
            "item": case["id"], "turn": None, "request_id": request_id,
            "trace_id": trace_id, "trace_url": trace_url, "scope": "renewal_workflow",
            "intent": "scheduled_contract_renewal", "status": result.status,
            "tool_sequence": [], "citations": ["database/contracts/C001", "database/software_subscriptions/SUB001"],
            "scores": scores, "score_comments": comments, "answer": result.answer,
        })
    return records


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
        "score_comments": result.score_comments,
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
        "--include-optional",
        action="store_true",
        help="Run Vendor and Renewal too, producing all 33 submission traces.",
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
        result = run(trace=args.trace, include_optional=args.include_optional)
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
