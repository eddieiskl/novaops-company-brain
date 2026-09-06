from __future__ import annotations

from evals.run_guardrail_attacks import run


def test_guardrail_attack_suite_passes() -> None:
    assert run() == []
