"""Lesson 15 acceptance: real process deaths and optional hosted traces."""

import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from maya import ops
from renewal import (
    InternalApprovalEvent,
    ProviderDecisionExtractor,
    build_renewal_workflow,
)
from renewal.runtime import DeterministicProviderModel


def workflow():
    return build_renewal_workflow(
        extractor=ProviderDecisionExtractor(model=DeterministicProviderModel()),
        security_reviewer_id="E006",
    )


def events():
    return [
        InternalApprovalEvent(**json.loads(s))
        for s in (ROOT / "evals/fixtures/lesson15/internal_approval_events.jsonl")
        .read_text()
        .splitlines()
    ]


def prepare(stage):
    w = workflow()
    if stage == "start":
        return
    w.start("2026-07-01")
    for event in events()[: 2 if stage == "internal" else 3]:
        w.handle_internal_event(event)
    if stage == "activation":
        w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved")


def crash(stage):
    w = workflow()

    def after(method):
        def wrapped(*args, **kwargs):
            method(*args, **kwargs)
            os._exit(91)  # Skip exception handlers and connection cleanup.

        return wrapped

    if stage == "start":
        w.notifications.send = after(w.notifications.send)
        w.start("2026-07-01")
    elif stage == "internal":
        w.provider_email.send = after(w.provider_email.send)
        w.handle_internal_event(events()[2])
    elif stage == "provider":
        w.store.record_agreement = after(w.store.record_agreement)
        w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved")
    else:
        w.notifications.send = after(w.notifications.send)
        w.start("2026-07-21")
    raise AssertionError("Crash point not reached")


def crash_checks():
    results = []
    original = os.environ.get("NOVAOPS_DB_PATH")
    try:
        with tempfile.TemporaryDirectory(
            prefix="lesson15-crash-", dir="/private/tmp"
        ) as folder:
            for stage in ("start", "internal", "provider", "activation"):
                os.environ["NOVAOPS_DB_PATH"] = str(Path(folder) / (stage + ".sqlite3"))
                ops.reset_conn(reseed=False)
                prepare(stage)
                ops.reset_conn(reseed=False)
                child = subprocess.run(
                    [sys.executable, __file__, "--crash-stage", stage],
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                )
                assert child.returncode == 91, (stage, child.stderr)
                ops.reset_conn(reseed=False)
                w = workflow()
                if stage == "start":
                    w.start("2026-07-01")
                elif stage == "internal":
                    w.handle_internal_event(events()[2])
                elif stage == "provider":
                    w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved")
                else:
                    w.start("2026-07-21")
                run = w.store.get_run("RR-WEBEX-2026")
                assert run
                if stage == "activation":
                    assert (
                        len(w.store.applied_updates(run["run_id"]))
                        == len(w.store.notifications(run["run_id"]))
                        == 1
                    )
                    w.start("2026-07-21")
                    assert (
                        len(w.store.applied_updates(run["run_id"]))
                        == len(w.store.notifications(run["run_id"]))
                        == 1
                    )
                results.append(
                    {
                        "stage": stage,
                        "child_exit": 91,
                        "recovered": True,
                        "state": run["stage"],
                    }
                )
            ops.reset_conn(reseed=False)
    finally:
        if original is None:
            os.environ.pop("NOVAOPS_DB_PATH", None)
        else:
            os.environ["NOVAOPS_DB_PATH"] = original
        ops.reset_conn(reseed=False)
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trace", action="store_true")
    p.add_argument(
        "--crash-stage", choices=["start", "internal", "provider", "activation"]
    )
    p.add_argument(
        "--output", type=Path, default=ROOT / "evals/results/lesson15-acceptance.json"
    )
    a = p.parse_args()
    if a.crash_stage:
        crash(a.crash_stage)
        return 1
    crashes = crash_checks()
    from run_submission import _run_renewal_cases, load_inputs, update_submission

    dataset = next(w for w in load_inputs()["workflows"] if w["id"] == "renewal")
    records = _run_renewal_cases(dataset, trace=a.trace)
    passed = all(all(value == 1 for value in r["scores"].values()) for r in records)
    report = {
        "passed": passed,
        "mode": "hosted-trace" if a.trace else "offline",
        "crash_checks": crashes,
        "records": records,
        "fixture_scope": "Local scope and clearance fixtures supplement older evaluation inputs; no real approvals or external messages.",
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2))
    if a.trace and passed:
        update_submission(records, ROOT / "SUBMISSION.md")
    print(
        json.dumps(
            {
                "passed": passed,
                "process_crash_checks": len(crashes),
                "renewal_cases": len(records),
                "trace_ids": [r["trace_id"] for r in records],
                "output": str(a.output),
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
