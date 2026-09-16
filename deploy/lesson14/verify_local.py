"""Run only against the isolated Lesson 14 Compose project; never print secrets."""
import json
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "-f", str(HERE / "compose.yaml")]
results = {}


def docker(*args):
    return subprocess.check_output(COMPOSE + list(args), cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def check(name, condition):
    results[name] = bool(condition)
    assert condition, name
    print(name + ": passed", flush=True)


def mcp(name, arguments):
    code = "import json; from company_brain.mcp_client import MCPToolClient; print(json.dumps(MCPToolClient('http://mcp:9880/mcp').call_sync(" + repr(name) + "," + repr(arguments) + ")))"
    return json.loads(docker("exec", "-T", "agent-api", "python", "-c", code))


def ready(client):
    for _ in range(40):
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise AssertionError("readiness did not recover")


def main():
    client = httpx.Client(base_url="http://127.0.0.1:18114", timeout=120)
    ready(client)
    for service in ["agent-api", "mcp", "gateway"]:
        check(service + "_nonroot", docker("exec", "-T", service, "id", "-u").strip() == "10001")
    proof = json.loads(docker("exec", "-T", "agent-api", "python", "-c",
        "import os,json,importlib.util,pathlib; print(json.dumps({'no_sdk':importlib.util.find_spec('boto3') is None,'no_adapter':not pathlib.Path('/app/bedrock_client.py').exists(),'no_documents':not pathlib.Path('/app/novaops-enterprise-agent-dataset/documents').exists(),'invalid_provider_key':os.environ.get('AWS_SECRET_ACCESS_KEY')=='deliberately-invalid'}))"))
    for name, passed in proof.items():
        check(name, passed)
    run = uuid.uuid4().hex[:10]
    base = {"thread_id": "live-" + run, "caller": {"employee_id": "E010", "user_group": "UG_REGULAR"}}
    for message in [" ", "x" * 12001]:
        check("validation_" + str(len(message)), client.post("/v1/agent/turn", json={**base, "message": message}).status_code == 422)
    answer = client.post("/v1/agent/turn", json={**base, "message": "May I use my own laptop for work?"})
    check("live_gateway_policy_answer", answer.status_code == 200 and answer.json()["status"] == "completed" and bool(answer.json()["citations"]))
    settings = dotenv_values(HERE / ".runtime/agent.env")
    gateway = httpx.Client(base_url="http://127.0.0.1:4114", timeout=90)
    headers = {"Authorization": "Bearer " + settings["LITELLM_API_KEY"]}
    payload = {"model": "unapproved-model", "messages": [{"role": "user", "content": "hello"}]}
    check("unapproved_model_rejected", gateway.post("/chat/completions", headers=headers, json=payload).status_code == 400)
    check("invalid_gateway_key_rejected", gateway.get("/models", headers={"Authorization": "Bearer invalid"}).status_code in [400, 401, 403])
    handoff = mcp("prepare_access_handoff", {"conversation_id": "live-approval-" + run, "subject_employee_id": "E001", "software": "Webex", "business_justification": "Customer meetings", "caller_employee_id": "E004", "idempotency_key": "live-approval-" + run})
    body = {"handoff_id": handoff["handoff_id"], "approval_id": handoff["approval_id"], "decision": "approved", "reason": "Approved for role"}
    check("approval_requires_auth", client.post("/v1/approvals/resume", json=body).status_code == 401)
    docker("restart", "mcp", "agent-api")
    ready(client)
    approval_headers = {"Authorization": "Bearer " + settings["NOVAOPS_APPROVAL_TOKEN"]}
    first = client.post("/v1/approvals/resume", headers=approval_headers, json=body)
    second = client.post("/v1/approvals/resume", headers=approval_headers, json=body)
    check("approval_survives_restart", first.status_code == 200 and first.json()["status"] == "blocked")
    check("approval_replay_same_request", second.status_code == 200 and first.json()["access_request"]["request_id"] == second.json()["access_request"]["request_id"])
    check("approval_conflict_rejected", client.post("/v1/approvals/resume", headers=approval_headers, json={**body, "decision": "rejected"}).status_code == 409)
    for service in ["mcp", "gateway"]:
        docker("stop", service)
        try:
            check(service + "_outage_ready503", client.get("/health/ready").status_code == 503)
            check(service + "_outage_live200", client.get("/health/live").status_code == 200)
        finally:
            docker("start", service)
            ready(client)
        check(service + "_recovered", True)
    results["release"] = client.get("/health/version").json()


if __name__ == "__main__":
    try:
        main()
    finally:
        (HERE / "evidence").mkdir(exist_ok=True)
        (HERE / "evidence/local-verification.json").write_text(json.dumps(results, indent=2) + "\n")
