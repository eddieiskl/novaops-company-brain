from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def load_binding_expectations(evaluation_dataset: dict[str, Any]) -> dict[tuple[str, int | None], dict[str, Any]]:
    """Map every required measured input to readable, binding expectations."""

    golden = json.loads((ROOT / "spec" / "GOLDEN-DATASETS.json").read_text(encoding="utf-8"))
    golden_sessions = {session["id"]: session for session in golden["sessions"]}
    session_mapping = {
        "M-S-01": "S2-onboarding-maya",
        "M-S-02": "S9-maya-own-account",
        "W-S-01": "S8-boundary-heavy-noise",
    }
    single_by_message = {_normalized(case["input"]): case for case in golden["single_turn_cases"]}
    webex_cases = json.loads((ROOT / "evals" / "webex_cases.json").read_text(encoding="utf-8"))["cases"]
    webex_by_message = {_normalized(case["request"]): case for case in webex_cases}

    supplements = {
        "W-I-01": {
            "origin": "evals supplemental check",
            "should_use_tools": True,
            "required_facts": ["T001", "open"],
            "forbidden_tools": ["create_access_request", "assign_webex_license"],
        },
        "W-I-02": {
            "origin": "evals supplemental check",
            "should_use_tools": True,
            "required_facts": [
                "does not record employee-to-seat assignments",
                "entitlement is not proof",
                "Rachel Stein",
                "Maya Cohen",
                "Noam Sharon",
            ],
            "forbidden_tools": ["create_access_request", "assign_webex_license"],
        },
    }

    expectations: dict[tuple[str, int | None], dict[str, Any]] = {}
    for workflow in evaluation_dataset["workflows"]:
        if not workflow.get("required"):
            continue
        for case in workflow.get("inputs", []):
            expectation = deepcopy(single_by_message.get(_normalized(case["message"]), {}))
            webex = webex_by_message.get(_normalized(case["message"]))
            if webex:
                expectation.update(deepcopy(webex))
                expectation["origin"] = f"evals/webex_cases.json:{webex['id']}"
            elif expectation:
                expectation["origin"] = f"spec/GOLDEN-DATASETS.json:{expectation['case_id']}"
            elif case["id"] in supplements:
                expectation = deepcopy(supplements[case["id"]])
            expectations[(case["id"], None)] = expectation

        for session in workflow.get("sessions", []):
            golden_id = session_mapping.get(session["id"])
            if not golden_id:
                continue
            golden_turns = {turn["n"]: turn for turn in golden_sessions[golden_id]["turns"]}
            for turn in session["turns"]:
                expectation = deepcopy(golden_turns[turn["n"]])
                expectation["origin"] = f"spec/GOLDEN-DATASETS.json:{golden_id}:turn:{turn['n']}"
                expectations[(session["id"], turn["n"])] = expectation
    return expectations


def _contains_alternative(text: str, expectation: str) -> bool:
    folded = text.casefold()
    return any(alternative.strip().casefold() in folded for alternative in expectation.split("|"))


def _source_present(citations: list[str], expected: str) -> bool:
    expected_folded = expected.casefold()
    return any(expected_folded in source.casefold() for source in citations)


def score_binding_expectation(result: Any, expectation: dict[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
    """Evaluate only fields declared binding by the supplied golden dataset."""

    scores: dict[str, float] = {}
    comments: dict[str, str] = {}

    if "required_facts" in expectation:
        missing = [fact for fact in expectation["required_facts"] if not _contains_alternative(result.answer, fact)]
        scores["binding_required_facts"] = float(not missing)
        comments["binding_required_facts"] = "all required facts present" if not missing else f"missing: {missing}"

    if "forbidden_facts" in expectation:
        leaked = [fact for fact in expectation["forbidden_facts"] if _contains_alternative(result.answer, fact)]
        scores["binding_forbidden_facts"] = float(not leaked)
        comments["binding_forbidden_facts"] = "no forbidden facts present" if not leaked else f"present: {leaked}"

    if "forbidden_tools" in expectation:
        called = [tool for tool in expectation["forbidden_tools"] if tool in result.tool_sequence]
        scores["binding_forbidden_tools"] = float(not called)
        comments["binding_forbidden_tools"] = "no forbidden tools called" if not called else f"called: {called}"

    if "expected_sources" in expectation:
        missing_sources = [
            source for source in expectation["expected_sources"] if not _source_present(result.citations, source)
        ]
        scores["binding_expected_sources"] = float(not missing_sources)
        comments["binding_expected_sources"] = (
            "all expected sources retrieved" if not missing_sources else f"missing: {missing_sources}"
        )

    if "forbidden_sources" in expectation:
        leaked_sources = [
            source for source in expectation["forbidden_sources"] if _source_present(result.citations, source)
        ]
        scores["binding_forbidden_sources"] = float(not leaked_sources)
        comments["binding_forbidden_sources"] = (
            "no forbidden sources retrieved" if not leaked_sources else f"retrieved: {leaked_sources}"
        )

    if "should_use_tools" in expectation:
        expected = bool(expectation["should_use_tools"])
        actual = bool(result.tool_sequence)
        scores["binding_tool_use"] = float(actual == expected)
        comments["binding_tool_use"] = f"expected tool use={expected}; observed={actual}"

    payload = result.payload
    if "expected_status" in expectation and hasattr(payload, "status"):
        actual_status = str(payload.status)
        expected_status = str(expectation["expected_status"])
        scores["binding_payload_status"] = float(actual_status == expected_status)
        comments["binding_payload_status"] = f"expected={expected_status}; observed={actual_status}"

    for field, attribute in (
        ("expected_ticket_id", "ticket_id"),
        ("expected_request_id", "access_request_id"),
        ("expected_granted_access", "granted_access"),
    ):
        if field in expectation and hasattr(payload, attribute):
            actual = getattr(payload, attribute)
            expected = expectation[field]
            name = f"binding_{field.removeprefix('expected_')}"
            scores[name] = float(actual == expected)
            comments[name] = f"expected={expected!r}; observed={actual!r}"

    return scores, comments


def expectation_label(expectation: dict[str, Any] | None) -> str:
    return str((expectation or {}).get("origin", "unmapped"))
