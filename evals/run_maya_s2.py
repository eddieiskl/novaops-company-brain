from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import CallerContext, FakeWebexPort, InMemoryEvidenceRetriever, MayaAgent


def run() -> list[str]:
    spec = json.loads((Path(__file__).with_name("context_sessions.json")).read_text())
    caller = CallerContext(**spec["caller"])
    port = FakeWebexPort()
    agent = MayaAgent(InMemoryEvidenceRetriever(), port)
    errors: list[str] = []
    results = []

    for turn in spec["turns"]:
        result = agent.handle_turn_sync(spec["id"], caller, turn["n"], turn["user"])
        results.append(result)
        calls = set(result.operational_tool_calls)
        if turn["n"] == 10 and result.handoffs:
            calls.add("webex_access")
        for tool in turn["expected_tools"]:
            if tool not in calls:
                errors.append(f"turn {turn['n']}: expected {tool}, got {sorted(calls)}")
        for tool in turn["forbidden_tools"]:
            if tool in calls:
                errors.append(f"turn {turn['n']}: forbidden {tool} was called")
        for fact in turn.get("required_facts", []):
            if fact not in result.answer:
                errors.append(f"turn {turn['n']}: missing fact {fact!r} in answer")
        for fact in turn.get("forbidden_facts", []):
            if fact in result.answer:
                errors.append(f"turn {turn['n']}: leaked closed tangent fact {fact!r}")

    if len(port.calls) != 1:
        errors.append(f"expected one Webex handoff, got {len(port.calls)}")

    final = results[-1].checklist
    sources = {c.source_path for c in final.all_citations()}
    for required in (
        "documents/employment/maya_cohen_offer_letter.md",
        "documents/it_kb/webex_license_assignment.md",
        "documents/contracts/webex_vendor_agreement.md",
    ):
        if required not in sources:
            errors.append(f"final checklist missing citation {required}")

    print("turn intent calls handoffs errors")
    for result in results:
        print(result.turn, result.intent, ",".join(result.operational_tool_calls) or "-", len(result.handoffs), ";".join(result.errors) or "-")
    print(f"webex_handoffs={len(port.calls)}")
    return errors


if __name__ == "__main__":
    failures = run()
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("\nS2 replay passed.")
