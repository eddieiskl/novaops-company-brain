from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

from run_webex_s8 import run


def test_s8_noisy_write_boundary_replay_passes() -> None:
    assert run() == []
