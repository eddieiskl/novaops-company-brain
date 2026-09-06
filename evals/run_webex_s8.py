from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain import CompanyBrainAgent
from maya import CallerContext, ops


def _matches(answer: str, expectation: str) -> bool:
    lowered = answer.lower()
    return any(item.strip().lower() in lowered for item in expectation.split("|"))


def run() -> list[str]:
    golden = json.loads((ROOT / "spec" / "GOLDEN-DATASETS.json").read_text(encoding="utf-8"))
    session = next(item for item in golden["sessions"] if item["id"] == "S8-boundary-heavy-noise")
    ops.reset_conn()
    agent = CompanyBrainAgent()
    caller = CallerContext("E004", "UG_HR")
    errors: list[str] = []

    for turn in session["turns"]:
        result = agent.handle_turn(session["id"], caller, turn["user"], turn=turn["n"])
        for fact in turn.get("required_facts", []):
            if not _matches(result.answer, fact):
                errors.append(f"turn {turn['n']}: missing required fact {fact!r}")
        for tool in turn.get("forbidden_tools", []):
            if tool in result.tool_sequence:
                errors.append(f"turn {turn['n']}: called forbidden tool {tool!r}")
        if turn.get("should_use_tools") is False and result.tool_sequence:
            errors.append(f"turn {turn['n']}: expected no tool call")
        if turn.get("should_use_tools") is True and not result.tool_sequence:
            errors.append(f"turn {turn['n']}: expected a tool call")
    return errors


if __name__ == "__main__":
    failures = run()
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print("S8 noisy write-boundary replay passed.")
