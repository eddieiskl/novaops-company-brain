from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from run_maya_s2 import run
from maya import CallerContext
from maya.policy import plan_turn


def test_complete_s2_replay_passes() -> None:
    assert run() == []
    caller = CallerContext("E004", "UG_HR")
    assert plan_turn(1, "Who is Maya and when does she start?", caller).intent == "employee_lookup"
    assert plan_turn(2, "Which systems does Maya need?", caller).intent == "offer_letter"
    assert plan_turn(3, "What is currently blocking onboarding?", caller).intent == "onboarding_status"
    assert plan_turn(4, "Is a Webex seat available for Maya?", caller).intent == "subscription_review"
    assert plan_turn(5, "Hello", caller).intent == "help"
    assert plan_turn(6, "Give me an overview of Maya's onboarding", caller).intent == "overview"
    assert plan_turn(7, "What equipment is ready for Maya?", caller).intent == "equipment_request"
    assert plan_turn(8, "Is Maya's laptop ready?", caller).intent == "equipment_request"
