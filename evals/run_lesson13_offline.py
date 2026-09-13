from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain import CompanyBrainAgent, DisabledRequestGuard, LocalRuleRequestGuard
from maya import CallerContext, ops


CASES = Path(__file__).with_name("lesson13_guard_cases.jsonl")


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]


def access_request_count() -> int:
    return int(ops.conn().execute("SELECT COUNT(*) FROM access_requests").fetchone()[0])


def run(*, write_report: bool = True) -> dict:
    cases = load_cases()
    records: list[dict] = []
    errors: list[str] = []

    for mode, guard in (("guarded", LocalRuleRequestGuard()), ("classifier_disabled", DisabledRequestGuard())):
        for case in cases:
            ops.reset_conn()
            before = access_request_count()
            caller = CallerContext(**case["caller"])
            result = CompanyBrainAgent(request_guard=guard).handle_turn(
                f"lesson13-{mode}-{case['id']}", caller, case["message"]
            )
            after = access_request_count()
            verdict = result.guard_decision
            row_errors: list[str] = []
            if mode == "guarded":
                if verdict.get("decision") != case["expected_guard"]:
                    row_errors.append(f"expected decision {case['expected_guard']}, got {verdict.get('decision')}")
                if verdict.get("category") != case["expected_category"]:
                    row_errors.append(f"expected category {case['expected_category']}, got {verdict.get('category')}")
            if after != before:
                row_errors.append(f"durable access-request count changed from {before} to {after}")
            forbidden = case.get("forbid_citation_fragment")
            if forbidden and any(forbidden in citation for citation in result.citations):
                row_errors.append(f"forbidden citation escaped authorization: {forbidden}")
            errors.extend(f"{mode}/{case['id']}: {error}" for error in row_errors)
            records.append(
                {
                    "id": case["id"],
                    "split": case["split"],
                    "kind": case["kind"],
                    "mode": mode,
                    "guard": verdict,
                    "status": result.status,
                    "intent": result.intent,
                    "tool_sequence": result.tool_sequence,
                    "citations": result.citations,
                    "access_requests_before": before,
                    "access_requests_after": after,
                    "errors": row_errors,
                }
            )

    guarded = [record for record in records if record["mode"] == "guarded"]
    report = {
        "provenance": {
            "mode": "cloud-free deterministic guard seam",
            "limitation": "No Bedrock classifier latency, tokens, semantic generalization, or live OpenSearch poisoning evidence is claimed.",
        },
        "dataset": {
            "cases": len(cases),
            "development": sum(case["split"] == "development" for case in cases),
            "held_out": sum(case["split"] == "held-out" for case in cases),
            "kinds": dict(Counter(case["kind"] for case in cases)),
        },
        "guarded_decisions": dict(Counter(record["guard"]["decision"] for record in guarded)),
        "classifier_disabled_effect_violations": sum(
            bool(record["errors"]) for record in records if record["mode"] == "classifier_disabled"
        ),
        "records": records,
        "errors": errors,
    }
    if write_report:
        output = ROOT / ".state" / "lesson13-offline-evaluation.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({key: result[key] for key in ("dataset", "guarded_decisions", "classifier_disabled_effect_violations", "errors")}, indent=2))
    raise SystemExit(1 if result["errors"] else 0)

