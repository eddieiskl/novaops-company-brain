from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env", override=False)

from maya import BedrockAnswerPort, CallerContext, FakeWebexPort, InMemoryEvidenceRetriever, MayaAgent


def _matches(answer: str, expectation: str) -> bool:
    lowered = answer.lower()
    return any(alternative.strip().lower() in lowered for alternative in expectation.split("|"))


def run() -> list[str]:
    dataset = json.loads((ROOT / "spec" / "GOLDEN-DATASETS.json").read_text(encoding="utf-8"))
    session = next(item for item in dataset["sessions"] if item["id"] == "S9-maya-own-account")
    answer_port = BedrockAnswerPort() if os.getenv("NOVAOPS_ANSWER_MODE") == "bedrock" else None
    agent = MayaAgent(InMemoryEvidenceRetriever(), FakeWebexPort(), answer_port=answer_port)
    caller = CallerContext(session["caller_id"], session["caller_group"])
    errors: list[str] = []

    for turn in session["turns"]:
        turn_number = turn["n"]
        result = agent.handle_turn_sync(session["id"], caller, turn_number, turn["user"])
        for fact in turn.get("required_facts", []):
            if not _matches(result.answer, fact):
                errors.append(f"turn {turn_number}: missing required fact {fact!r}")
        for fact in turn.get("forbidden_facts", []):
            if _matches(result.answer, fact):
                errors.append(f"turn {turn_number}: included forbidden fact {fact!r}")
        paths = [chunk.source_path for chunk in result.retrieved]
        for source in turn.get("expected_sources", []):
            if not any(source in path for path in paths):
                errors.append(f"turn {turn_number}: missing source {source!r}")
        for source in turn.get("forbidden_sources", []):
            if any(source in path for path in paths):
                errors.append(f"turn {turn_number}: leaked source {source!r}")
        for tool in turn.get("forbidden_tools", []):
            if tool in result.operational_tool_calls:
                errors.append(f"turn {turn_number}: called forbidden tool {tool!r}")
        if turn.get("should_use_tools") is False and result.operational_tool_calls:
            errors.append(f"turn {turn_number}: should not use tools")

    return errors


if __name__ == "__main__":
    failures = run()
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print("S9 replay passed.")
