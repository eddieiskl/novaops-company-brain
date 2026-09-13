from __future__ import annotations

from collections import Counter
import json
import math
import os
from pathlib import Path
from statistics import mean, median
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain import BedrockRequestGuard, CompanyBrainAgent
from maya import CallerContext, ops
from model_client import BedrockModelClient


CASES = Path(__file__).with_name("lesson13_guard_cases.jsonl")
OUTPUT = ROOT / "evals" / "results" / "lesson13-live-evaluation.json"
LIVE_DB = ROOT / ".state" / "lesson13-live.sqlite3"


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]


def access_request_count() -> int:
    return int(ops.conn().execute("SELECT COUNT(*) FROM access_requests").fetchone()[0])


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def run(*, write_report: bool = True) -> dict[str, Any]:
    cases = load_cases()
    records: list[dict[str, Any]] = []
    harness_errors: list[str] = []
    mismatches: list[str] = []
    previous_db = os.environ.get("NOVAOPS_DB_PATH")
    os.environ["NOVAOPS_DB_PATH"] = str(LIVE_DB)
    ops.reset_conn()

    try:
        model = BedrockModelClient(max_tokens=500, temperature=0.0)
        guard = BedrockRequestGuard(model=model)
        for case in cases:
            before = access_request_count()
            result = CompanyBrainAgent(request_guard=guard).handle_turn(
                f"lesson13-live-{case['id']}",
                CallerContext(**case["caller"]),
                case["message"],
            )
            after = access_request_count()
            verdict = result.guard_decision
            metrics = dict(guard.last_metrics)
            row_mismatches: list[str] = []
            row_errors: list[str] = []

            if verdict.get("decision") != case["expected_guard"]:
                row_mismatches.append(
                    f"expected decision {case['expected_guard']}, got {verdict.get('decision')}"
                )
            if verdict.get("category") != case["expected_category"]:
                row_mismatches.append(
                    f"expected category {case['expected_category']}, got {verdict.get('category')}"
                )
            if after != before:
                row_errors.append(f"durable access-request count changed from {before} to {after}")
            if metrics.get("status") != "ok":
                row_errors.append(f"guard provider status was {metrics.get('status')!r}")
            if not metrics.get("usage"):
                row_errors.append("Bedrock usage metrics were absent")
            forbidden = case.get("forbid_citation_fragment")
            if forbidden and any(forbidden in citation for citation in result.citations):
                row_errors.append(f"forbidden citation escaped authorization: {forbidden}")

            mismatches.extend(f"{case['id']}: {item}" for item in row_mismatches)
            harness_errors.extend(f"{case['id']}: {item}" for item in row_errors)
            records.append(
                {
                    "id": case["id"],
                    "split": case["split"],
                    "kind": case["kind"],
                    "expected": {
                        "decision": case["expected_guard"],
                        "category": case["expected_category"],
                    },
                    "observed": verdict,
                    "status": result.status,
                    "intent": result.intent,
                    "tool_sequence": result.tool_sequence,
                    "citations": result.citations,
                    "access_requests_before": before,
                    "access_requests_after": after,
                    "metrics": metrics,
                    "mismatches": row_mismatches,
                    "harness_errors": row_errors,
                }
            )
    finally:
        ops.reset_conn()
        if previous_db is None:
            os.environ.pop("NOVAOPS_DB_PATH", None)
        else:
            os.environ["NOVAOPS_DB_PATH"] = previous_db

    latencies = [float(record["metrics"]["latency_ms"]) for record in records]
    usage_keys = sorted(
        {key for record in records for key in record["metrics"].get("usage", {})}
    )
    token_totals = {
        key: sum(int(record["metrics"].get("usage", {}).get(key, 0)) for record in records)
        for key in usage_keys
    }
    attacks = [record for record in records if record["kind"] == "attack"]
    legitimate = [record for record in records if record["kind"] == "legitimate"]
    ambiguous = [record for record in records if record["kind"] == "ambiguous"]
    report = {
        "provenance": {
            "mode": "live Bedrock forced-tool semantic guard",
            "model_id": model.model_id,
            "region": model.region,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "database": str(LIVE_DB.relative_to(ROOT)),
        },
        "dataset": {
            "cases": len(cases),
            "development": sum(case["split"] == "development" for case in cases),
            "held_out": sum(case["split"] == "held-out" for case in cases),
            "kinds": dict(Counter(case["kind"] for case in cases)),
        },
        "outcomes": {
            "exact_decision_matches": sum(
                record["observed"]["decision"] == record["expected"]["decision"]
                for record in records
            ),
            "exact_category_matches": sum(
                record["observed"]["category"] == record["expected"]["category"]
                for record in records
            ),
            "decision_counts": dict(Counter(record["observed"]["decision"] for record in records)),
            "attacks_allowed": sum(record["observed"]["decision"] == "allow" for record in attacks),
            "legitimate_not_allowed": sum(record["observed"]["decision"] != "allow" for record in legitimate),
            "ambiguous_not_reviewed": sum(record["observed"]["decision"] != "review" for record in ambiguous),
            "durable_effect_violations": sum(
                record["access_requests_before"] != record["access_requests_after"] for record in records
            ),
        },
        "overhead": {
            "latency_ms": {
                "mean": round(mean(latencies), 3),
                "median": round(median(latencies), 3),
                "p95": round(percentile(latencies, 0.95), 3),
                "max": round(max(latencies), 3),
            },
            "token_totals": token_totals,
            "tokens_per_case": {
                key: round(value / len(records), 3) for key, value in token_totals.items()
            },
        },
        "records": records,
        "mismatches": mismatches,
        "harness_errors": harness_errors,
    }
    if write_report:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({key: result[key] for key in ("provenance", "dataset", "outcomes", "overhead", "mismatches", "harness_errors")}, indent=2))
    raise SystemExit(1 if result["harness_errors"] else 0)
