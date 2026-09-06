from __future__ import annotations

import json
from pathlib import Path

from maya import ops
from renewal import InternalApprovalEvent, ProviderDecisionExtractor, build_renewal_workflow


ROOT = Path(__file__).resolve().parents[1]
RENEWAL_ROOT = ROOT / "novaops-enterprise-agent-dataset" / "workflows" / "renewal"


class FakeProviderModel:
    model_id = "fake-provider-model"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract_with_tool(self, prompt: str, **kwargs) -> dict:
        self.calls.append(prompt)
        if "webex_renewal_approved" in prompt:
            return {
                "contract_id": "C001",
                "decision": "approved",
                # Exercise source-grounded recovery when the model emits nulls.
                "confirmation_id": None,
                "new_seat_limit": 50,
                "annual_cost_usd": 22000,
                "term_start_date": None,
                "term_end_date": None,
                "conditions": [],
            }
        if "webex_renewal_conditional" in prompt:
            return {
                "contract_id": "C001",
                "decision": "conditional",
                "confirmation_id": None,
                "new_seat_limit": 50,
                "annual_cost_usd": 22000,
                "term_start_date": "2026-07-21",
                "term_end_date": "2027-07-20",
                "conditions": ["Signed order form", "Written Finance acceptance"],
            }
        return {
            "contract_id": None,
            "decision": "ambiguous",
            "confirmation_id": None,
            "new_seat_limit": 50,
            # Bedrock can emit numeric sentinels for absent optional values.
            "annual_cost_usd": -1,
            "term_start_date": None,
            "term_end_date": None,
            "conditions": ["Billing review and final confirmation still pending"],
        }


def _approval_event() -> InternalApprovalEvent:
    row = json.loads((RENEWAL_ROOT / "internal_approval_events.jsonl").read_text().splitlines()[0])
    return InternalApprovalEvent(**row)


def _reply(fixture_id: str) -> str:
    return (RENEWAL_ROOT / "provider_replies" / f"{fixture_id}.eml").read_text(encoding="utf-8")


def _restart(model: FakeProviderModel):
    ops.reset_conn(reseed=False)
    return build_renewal_workflow(extractor=ProviderDecisionExtractor(model=model))


def test_approved_renewal_survives_restarts_and_replays_exactly_once() -> None:
    ops.reset_conn()
    model = FakeProviderModel()
    started = build_renewal_workflow(extractor=ProviderDecisionExtractor(model=model)).start("2026-07-01")
    assert started.run_id == "RR-WEBEX-2026"
    assert started.status == "pending"

    approved = _restart(model).handle_internal_event(_approval_event())
    assert approved.stage == "awaiting_provider_reply"

    workflow = _restart(model)
    result = workflow.handle_provider_reply(started.run_id, "webex_renewal_approved", _reply("webex_renewal_approved"))
    replay = workflow.handle_provider_reply(started.run_id, "webex_renewal_approved", _reply("webex_renewal_approved"))

    assert result.status == "completed"
    assert result.applied is True
    assert result.notified_employee_ids == ["E010"]
    assert replay.applied is True
    assert len(model.calls) == 1
    subscription = ops.conn().execute(
        "SELECT seat_limit, annual_cost, renewal_date FROM software_subscriptions WHERE subscription_id = 'SUB001'"
    ).fetchone()
    assert dict(subscription) == {"seat_limit": 50, "annual_cost": 22000, "renewal_date": "2027-07-20"}
    assert len(workflow.store.applied_updates(started.run_id)) == 1
    assert len(workflow.store.notifications(started.run_id)) == 1
    assert ops.conn().execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE event_id = 'EV-RR-WEBEX-2026-APPLIED'"
    ).fetchone()["n"] == 1


def test_conditional_and_ambiguous_replies_make_no_business_update() -> None:
    for fixture_id in ("webex_renewal_conditional", "webex_renewal_ambiguous"):
        ops.reset_conn()
        model = FakeProviderModel()
        workflow = build_renewal_workflow(extractor=ProviderDecisionExtractor(model=model))
        started = workflow.start("2026-07-01")
        workflow.handle_internal_event(_approval_event())
        result = workflow.handle_provider_reply(started.run_id, fixture_id, _reply(fixture_id))

        assert result.status == "needs_human"
        assert result.applied is False
        assert result.notified_employee_ids == []
        subscription = ops.conn().execute(
            "SELECT seat_limit, annual_cost FROM software_subscriptions WHERE subscription_id = 'SUB001'"
        ).fetchone()
        assert dict(subscription) == {"seat_limit": 40, "annual_cost": 18400}
        assert workflow.store.applied_updates(started.run_id) == []
        assert workflow.store.notifications(started.run_id) == []


def test_wrong_approver_and_mismatched_contract_fail_closed() -> None:
    ops.reset_conn()
    model = FakeProviderModel()
    workflow = build_renewal_workflow(extractor=ProviderDecisionExtractor(model=model))
    started = workflow.start("2026-07-01")
    event = _approval_event()
    wrong = InternalApprovalEvent(**{**event.__dict__, "actor_employee_id": "E011"})

    try:
        workflow.handle_internal_event(wrong)
    except PermissionError:
        pass
    else:
        raise AssertionError("wrong approver must fail closed")

    workflow.handle_internal_event(event)
    class MismatchModel(FakeProviderModel):
        def extract_with_tool(self, prompt: str, **kwargs) -> dict:
            result = super().extract_with_tool(prompt, **kwargs)
            result["contract_id"] = "C999"
            return result

    mismatched = build_renewal_workflow(extractor=ProviderDecisionExtractor(model=MismatchModel()))
    result = mismatched.handle_provider_reply(started.run_id, "webex_renewal_approved", _reply("webex_renewal_approved"))
    assert result.status == "needs_human"
    assert result.applied is False
