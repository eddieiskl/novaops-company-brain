from __future__ import annotations

from evals.run_lesson13_offline import run


def test_lesson13_offline_evaluation_passes() -> None:
    report = run(write_report=False)

    assert report["dataset"] == {
        "cases": 16,
        "development": 12,
        "held_out": 4,
        "kinds": {"attack": 8, "legitimate": 6, "ambiguous": 2},
    }
    assert report["classifier_disabled_effect_violations"] == 0
    assert report["errors"] == []

