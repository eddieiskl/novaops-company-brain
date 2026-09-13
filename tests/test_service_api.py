from __future__ import annotations

from fastapi.testclient import TestClient

from maya import ops
from service import api


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("NOVAOPS_TOOL_MODE", "local")
    monkeypatch.setenv("NOVAOPS_ANSWER_MODE", "deterministic")
    api._agent = None
    ops.reset_conn()
    return TestClient(api.app)


def test_health_checks_are_cheap_and_model_free(monkeypatch) -> None:
    client = _client(monkeypatch)

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready", "tool_mode": "local"}


def test_version_reports_the_immutable_release(monkeypatch) -> None:
    release = "a" * 40
    monkeypatch.setenv("NOVAOPS_RELEASE_SHA", release)
    response = _client(monkeypatch).get("/health/version")
    assert response.status_code == 200
    assert response.json() == {"release_sha": release}


def test_version_fails_closed_for_invalid_release(monkeypatch) -> None:
    monkeypatch.setenv("NOVAOPS_RELEASE_SHA", "latest")
    response = _client(monkeypatch).get("/health/version")
    assert response.status_code == 503


def test_agent_endpoint_uses_the_same_core_contract(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/v1/agent/turn",
        json={
            "thread_id": "api-test",
            "caller": {"employee_id": "E010", "user_group": "UG_REGULAR"},
            "message": "May I use my own laptop for work?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_scope"] == "maya_hr"
    assert body["intent"] == "personal_device_policy"
    assert body["status"] == "completed"


def test_api_rejects_blank_oversized_and_extra_input_before_workflow(monkeypatch) -> None:
    client = _client(monkeypatch)
    base = {
        "thread_id": "api-validation",
        "caller": {"employee_id": "E010", "user_group": "UG_REGULAR"},
    }
    assert client.post("/v1/agent/turn", json={**base, "message": ""}).status_code == 422
    assert client.post("/v1/agent/turn", json={**base, "message": "x" * 12_001}).status_code == 422
    assert client.post("/v1/agent/turn", json={**base, "message": "hello", "surprise": True}).status_code == 422


def test_vendor_endpoint_returns_locally_validated_record(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/v1/vendor/extract",
        json={
            "source_id": "formal_vendor_intake",
            "source_type": "formal_document",
            "document": "Vendor: HelioDesk",
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["missing_required_fields"] == []


def test_vendor_endpoint_rejects_unknown_offline_fixture(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/v1/vendor/extract",
        json={
            "source_id": "unknown_vendor",
            "source_type": "email_chain",
            "document": "Vendor Acme Cloud has an annual cost of USD 12,000.",
        },
    )

    assert response.status_code == 422
    assert "NOVAOPS_ANSWER_MODE=bedrock" in response.json()["detail"]
