from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from run_maya_s9 import run


def test_complete_s9_replay_passes_permission_and_context_checks() -> None:
    assert run() == []
