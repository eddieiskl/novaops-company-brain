from dataclasses import replace
from pathlib import Path
import json
import pytest
from maya import ops
from renewal import (
    InternalApprovalEvent,
    ProviderDecisionExtractor,
    build_renewal_workflow,
)
from renewal.runtime import DeterministicProviderModel

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVAOPS_DB_PATH", str(tmp_path / "renewal.sqlite3"))
    ops.reset_conn()
    yield
    ops.reset_conn(reseed=False)


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


def ready():
    w = workflow()
    w.start("2026-07-01")
    for e in events():
        w.handle_internal_event(e)
    return w


def test_AC01_AC02_AC03_portfolio_context_and_recommendations():
    w = workflow()
    reviews = w.scan("2026-07-01")
    webex = next(r for r in reviews if r["facts"]["contract_id"] == "C001")
    assert webex["facts"]["urgent"] and not webex["facts"]["expired"]
    assert webex["facts"]["notice_deadline"] == "2026-06-05"
    assert webex["facts"]["seat_limit"] == 40 and webex["facts"]["active_seats"] == 42
    assert webex["recommendation"]["action"] == "expand"
    support = next(r for r in reviews if r["facts"]["system_name"] == "SupportDesk")
    assert support["recommendation"]["action"] == "escalate"
    assert all(r["recommendation"]["evidence"] for r in reviews)


@pytest.mark.parametrize("missing", [0, 1, 2])
def test_AC04_each_precondition_is_required(missing):
    w = workflow()
    w.start("2026-07-01")
    for i, e in enumerate(events()):
        if i != missing:
            w.handle_internal_event(e)
    assert not [
        m
        for m in w.store.outbox("RR-WEBEX-2026")
        if m["kind"] == "provider_renewal_request"
    ]
    with pytest.raises(PermissionError):
        w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved")


def test_AC04_missing_scope_and_wrong_actor_fail_closed():
    w = workflow()
    w.start("2026-07-01")
    with pytest.raises(ValueError):
        w.handle_internal_event(replace(events()[0], approved_scope=None))
    with pytest.raises(PermissionError):
        w.handle_internal_event(replace(events()[0], actor_employee_id="E010"))
    assert not w.store.processed(events()[0].event_id)


def test_AC05_AC06_AC07_AC09_AC10_AC11_full_replay():
    w = ready()
    rid = "RR-WEBEX-2026"
    assert (
        len([m for m in w.store.outbox(rid) if m["kind"] == "provider_renewal_request"])
        == 1
    )
    result = w.handle_provider_reply(rid, "webex_renewal_approved")
    assert result.stage == "awaiting_effective_date" and not result.applied
    assert (
        w.store.db.execute(
            "SELECT seat_limit FROM software_subscriptions WHERE subscription_id='SUB001'"
        ).fetchone()[0]
        == 40
    )
    assert not w.store.notifications(rid)
    assert w.store.agreement(rid)["approval_event_id"] == events()[0].event_id
    ops.reset_conn(reseed=False)
    w = workflow()
    w.start("2026-07-20")
    assert not w.store.applied_updates(rid)
    result = w.start("2026-07-21")
    assert result.applied
    for e in events():
        w.handle_internal_event(e)
    w.handle_provider_reply(rid, "webex_renewal_approved")
    w.start("2026-07-21")
    assert len(w.store.applied_updates(rid)) == len(w.store.notifications(rid)) == 1
    row = w.store.db.execute(
        "SELECT seat_limit,active_seats FROM software_subscriptions WHERE subscription_id='SUB001'"
    ).fetchone()
    assert tuple(row) == (50, 42)
    messages = [m for m in w.store.outbox(rid) if m["kind"] == "blocker_changed"]
    assert (
        len(messages) == 1
        and "22000" not in messages[0]["body"]
        and "USD" not in messages[0]["body"]
    )
    assert "does not grant access" in messages[0]["body"]
    assert (
        w.store.db.execute(
            "SELECT status FROM access_requests WHERE request_id='AR001'"
        ).fetchone()[0]
        == "blocked"
    )


@pytest.mark.parametrize(
    "fixture",
    ["webex_renewal_conditional", "webex_renewal_ambiguous", "webex_renewal_rejected"],
)
def test_AC08_nonfinal_replies_stay_visible(fixture):
    w = ready()
    result = w.handle_provider_reply("RR-WEBEX-2026", fixture)
    assert result.status == "needs_human" and not result.applied
    assert w.store.get_run(result.run_id)["next_action"]
    assert not w.store.agreement(result.run_id)


def test_AC08_scope_ceiling_mismatch():
    w = workflow()
    w.start("2026-07-01")
    ev = events()
    ev[0] = replace(
        ev[0], approved_scope={**ev[0].approved_scope, "annual_cost_ceiling_usd": 21000}
    )
    for e in ev:
        w.handle_internal_event(e)
    assert (
        w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved").status
        == "needs_human"
    )


def test_AC09_changed_event_payload_rejected():
    w = ready()
    with pytest.raises(ValueError):
        w.handle_internal_event(replace(events()[0], decision="rejected"))


def test_AC09_activation_crash_rolls_back_effect_and_notifications(monkeypatch):
    w = ready()
    w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved")
    original = w.notifications.send

    def crash(**kwargs):
        original(**kwargs)
        raise RuntimeError("crash after enqueue")

    monkeypatch.setattr(w.notifications, "send", crash)
    with pytest.raises(RuntimeError):
        w.start("2026-07-21")
    ops.reset_conn(reseed=False)
    w = workflow()
    assert not w.store.applied_updates("RR-WEBEX-2026")
    assert (
        w.store.db.execute(
            "SELECT seat_limit FROM software_subscriptions WHERE subscription_id='SUB001'"
        ).fetchone()[0]
        == 40
    )
    assert w.start("2026-07-21").applied
    assert len(w.store.notifications("RR-WEBEX-2026")) == 1


def test_AC04_security_owner_must_be_configured():
    w = build_renewal_workflow(
        extractor=ProviderDecisionExtractor(model=DeterministicProviderModel())
    )
    w.start("2026-07-01")
    with pytest.raises(PermissionError):
        w.handle_internal_event(events()[2])


def test_AC09_timeout_and_restart_keep_delivery_uncertain():
    from renewal.adapters import OutboxDispatcher

    w = ready()
    message = next(
        m
        for m in w.store.outbox("RR-WEBEX-2026")
        if m["kind"] == "provider_renewal_request"
    )
    calls = []

    def timeout(msg):
        calls.append(msg)
        raise TimeoutError("remote result unknown")

    d = OutboxDispatcher(w.store, timeout)
    assert d.deliver(message["message_id"]) == "uncertain"
    assert d.deliver(message["message_id"]) == "uncertain" and len(calls) == 1
    with w.store.atomic():
        w.store.db.execute(
            "UPDATE renewal_outbox SET delivery_status='sending' WHERE message_id=?",
            (message["message_id"],),
        )
    ops.reset_conn(reseed=False)
    w = workflow()
    OutboxDispatcher(w.store, timeout).recover()
    assert (
        next(
            m
            for m in w.store.outbox("RR-WEBEX-2026")
            if m["message_id"] == message["message_id"]
        )["delivery_status"]
        == "uncertain"
    )


def test_AC09_internal_enqueue_crash_does_not_lose_event(monkeypatch):
    w = workflow()
    w.start("2026-07-01")
    for e in events()[:2]:
        w.handle_internal_event(e)
    original = w.provider_email.send

    def crash(**kwargs):
        original(**kwargs)
        raise RuntimeError("crash after enqueue")

    monkeypatch.setattr(w.provider_email, "send", crash)
    with pytest.raises(RuntimeError):
        w.handle_internal_event(events()[2])
    ops.reset_conn(reseed=False)
    w = workflow()
    assert not w.store.processed(events()[2].event_id)
    w.handle_internal_event(events()[2])
    assert (
        len(
            [
                m
                for m in w.store.outbox("RR-WEBEX-2026")
                if m["kind"] == "provider_renewal_request"
            ]
        )
        == 1
    )


def test_AC09_provider_record_crash_is_replayable(monkeypatch):
    w = ready()
    original = w.store.record_agreement

    def crash(*args):
        original(*args)
        raise RuntimeError("crash after agreement")

    monkeypatch.setattr(w.store, "record_agreement", crash)
    with pytest.raises(RuntimeError):
        w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved")
    ops.reset_conn(reseed=False)
    w = workflow()
    assert not w.store.agreement("RR-WEBEX-2026")
    assert (
        w.handle_provider_reply("RR-WEBEX-2026", "webex_renewal_approved").stage
        == "awaiting_effective_date"
    )


def test_AC04_scope_cannot_change_under_existing_clearances():
    w = workflow()
    w.start("2026-07-01")
    w.handle_internal_event(events()[0])
    w.handle_internal_event(events()[1])
    changed = replace(
        events()[0],
        event_id="amendment",
        approved_scope={**events()[0].approved_scope, "new_seat_limit": 60},
    )
    with pytest.raises(ValueError):
        w.handle_internal_event(changed)
    assert (
        json.loads(w.store.get_run("RR-WEBEX-2026")["approved_scope_json"])[
            "new_seat_limit"
        ]
        == 50
    )


def test_AC04_action_must_match_seat_change():
    w = workflow()
    w.start("2026-07-01")
    invalid = replace(
        events()[0], approved_scope={**events()[0].approved_scope, "action": "reduce"}
    )
    with pytest.raises(ValueError):
        w.handle_internal_event(invalid)


@pytest.mark.parametrize(
    "old,new",
    [
        ("contract C001", "contract unspecified"),
        ("confirmation RX-WEBEX-2026-8841", "confirmation unspecified"),
        ("to 50 seats", "to more seats"),
        ("USD 22,000", "an unspecified amount"),
        ("begins 2026-07-21", "begins later"),
        ("ends 2027-07-20", "ends later"),
        ("approved without further", "not approved without further"),
        ("final confirmation", "not final confirmation"),
        ("USD 22,000.", "USD 22,000. The annual price is USD 30,000."),
    ],
)
def test_source_omissions_contradictions_and_negation_cannot_be_filled_by_model(
    old, new
):
    # A model confidently repeats every fact from the original fixture even when
    # the actual message omits, contradicts or negates one of those facts.
    source = (
        ROOT
        / "novaops-enterprise-agent-dataset/workflows/renewal/provider_replies/webex_renewal_approved.eml"
    ).read_text()
    normalized = (
        ProviderDecisionExtractor(model=DeterministicProviderModel())
        .extract("webex_renewal_approved", source)
        .as_dict()
    )

    class OverconfidentModel:
        model_id = "overconfident-fixture"

        def extract_with_tool(self, *args, **kwargs):
            return normalized

    w = ready()
    w.extractor = ProviderDecisionExtractor(model=OverconfidentModel())
    assert old in source
    result = w.handle_provider_reply(
        "RR-WEBEX-2026", "webex_renewal_approved", source.replace(old, new)
    )
    assert result.status == "needs_human"
    assert not result.applied
    w.start("2026-07-21")
    assert not w.store.applied_updates("RR-WEBEX-2026")
    assert not w.store.notifications("RR-WEBEX-2026")
