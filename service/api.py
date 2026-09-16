from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from threading import Lock
import hmac
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Header, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
import httpx

from company_brain import build_company_brain_from_env
from company_brain.mcp_client import MCPToolClient
from company_brain.tools import LocalToolGateway, RemoteMCPToolGateway
from maya import CallerContext, ops
from vendor.runtime import extract_request
from vendor.reliability import VendorSchemaError


ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="NovaOps Company Brain", version="0.1.0")
_agent = None
_agent_lock = Lock()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_whitespace_only(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("value must not be blank")
        return value


class CallerInput(StrictModel):
    employee_id: str = Field(min_length=2, max_length=32, pattern=r"^E[0-9]+$")
    user_group: Literal["UG_REGULAR", "UG_HR", "UG_IT"]


class AgentTurnRequest(StrictModel):
    thread_id: str = Field(min_length=1, max_length=128)
    caller: CallerInput
    message: str = Field(min_length=1, max_length=12_000)
    turn: int | None = Field(default=None, ge=1, le=1_000)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class AgentTurnResponse(StrictModel):
    request_id: str
    thread_id: str
    turn: int
    workflow_scope: Literal["maya_hr", "webex_ops", "security_boundary"]
    intent: str
    status: Literal["completed", "blocked", "pending", "needs_human", "failed"]
    answer: str
    tool_sequence: list[str]
    citations: list[str]
    retryable: bool = False


class VendorExtractionRequest(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    source_type: Literal["formal_document", "email_chain", "call_transcript"]
    document: str = Field(min_length=1, max_length=100_000)


class VendorExtractionResponse(StrictModel):
    status: Literal["completed"]
    result: dict[str, Any]


class ReleaseResponse(StrictModel):
    release_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class ApprovalResumeRequest(StrictModel):
    handoff_id: str = Field(pattern=r"^HO-[A-F0-9]{12}$")
    approval_id: str = Field(pattern=r"^AP-H-[A-F0-9]{12}$")
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)


class ApprovalResumeResponse(StrictModel):
    handoff_id: str
    status: Literal["blocked", "pending"]
    released: bool
    reason: str
    approval_ids: list[str]
    access_request: dict[str, Any] | None


STATUS_CODES = {"completed": 200, "blocked": 200, "pending": 202,
                "needs_human": 409, "failed": 502}


def _tool_gateway():
    if os.getenv("NOVAOPS_TOOL_MODE", "local") == "mcp":
        return RemoteMCPToolGateway(os.getenv("NOVAOPS_MCP_URL", "http://127.0.0.1:9880/mcp"))
    return LocalToolGateway()


def _company_brain():
    global _agent
    if _agent is None:
        _agent = build_company_brain_from_env()
    return _agent


@app.get("/health/live")
def liveness() -> dict[str, str]:
    """Process-only health check; never calls a model or dependency."""
    return {"status": "ok"}


@app.get("/health/version", response_model=ReleaseResponse)
def version() -> ReleaseResponse:
    """Expose the immutable release identity without touching a model or dependency."""
    release_sha = os.getenv("NOVAOPS_RELEASE_SHA", "0" * 40).strip().lower()
    if len(release_sha) != 40 or any(char not in "0123456789abcdef" for char in release_sha):
        raise HTTPException(status_code=503, detail="release identity unavailable")
    return ReleaseResponse(release_sha=release_sha)


@app.get("/health/ready")
def readiness() -> dict[str, Any]:
    """Check local data and the selected tool boundary, without a model call."""
    mode = os.getenv("NOVAOPS_TOOL_MODE", "local").strip().lower()
    try:
        if mode == "mcp":
            url = os.getenv("NOVAOPS_MCP_URL", "http://127.0.0.1:9880/mcp")
            discovered = MCPToolClient(url).discover_sync()
            if not discovered:
                raise RuntimeError("MCP exposed no tools")
        else:
            ops.conn().execute("SELECT 1").fetchone()
        if os.getenv("NOVAOPS_ANSWER_MODE") == "gateway":
            base = os.environ["LITELLM_BASE_URL"].rstrip("/")
            # Authenticated model listing tests the gateway without spending tokens.
            r = httpx.get(base + "/models", headers={"Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]}, timeout=3)
            r.raise_for_status()
            if os.getenv("LITELLM_MODEL", "novaops-approved") not in {m["id"] for m in r.json()["data"]}:
                raise RuntimeError("approved model unavailable")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"tool dependency unavailable: {type(exc).__name__}") from exc
    return {"status": "ready", "tool_mode": mode}


@app.post("/v1/agent/turn", response_model=AgentTurnResponse)
def agent_turn(request: AgentTurnRequest, response: Response) -> AgentTurnResponse:
    with _agent_lock:
        result = _company_brain().handle_turn(
            request.thread_id,
            CallerContext(request.caller.employee_id, request.caller.user_group),
            request.message,
            turn=request.turn,
            request_id=request.request_id,
        )
    # The core intentionally has a deterministic fallback; a model-backed service
    # must expose the dependency failure instead of claiming a successful model turn.
    errors = getattr(result.payload, "errors", [])
    if os.getenv("NOVAOPS_ANSWER_MODE") == "gateway" and any(str(e).startswith("model_answer_fallback:") for e in errors):
        result.status = "failed"
        result.answer = "The model dependency failed. No automatic retry was performed."
    if result.status != "failed" and any(
        getattr(handoff, "status", None) == "pending_approval"
        for handoff in getattr(result.payload, "handoffs", [])
    ):
        result.status = "pending"
    response.status_code = STATUS_CODES[result.status]
    return AgentTurnResponse(
        request_id=result.request_id,
        thread_id=result.thread_id,
        turn=result.turn,
        workflow_scope=result.scope,
        intent=result.intent,
        status=result.status,
        answer=result.answer,
        tool_sequence=result.tool_sequence,
        citations=result.citations,
    )


@app.post("/v1/approvals/resume", response_model=ApprovalResumeResponse)
def approval_resume(request: ApprovalResumeRequest, response: Response,
                    authorization: str | None = Header(default=None)) -> ApprovalResumeResponse:
    token = os.getenv("NOVAOPS_APPROVAL_TOKEN")
    actor = os.getenv("NOVAOPS_APPROVER_ID")
    if not token or not actor:
        raise HTTPException(status_code=503, detail="Approval integration is not configured")
    if not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(status_code=401, detail="Invalid approval credential")
    # Actor identity comes from the authenticated integration, never from JSON/model text.
    with _agent_lock:
        result = _tool_gateway().call("approve_and_resume_handoff", {
            **request.model_dump(), "actor_employee_id": actor})
    if "error_code" in result:
        code = {"not_found": 404, "invalid_scope": 422, "forbidden": 403, "conflict": 409}[result["error_code"]]
        raise HTTPException(status_code=code, detail=result["error_code"])
    response.status_code = STATUS_CODES[result["status"]]
    return ApprovalResumeResponse.model_validate(result)


@app.post("/v1/vendor/extract", response_model=VendorExtractionResponse)
def vendor_extract(request: VendorExtractionRequest) -> VendorExtractionResponse:
    try:
        result = extract_request(
            request.source_id,
            request.source_type,
            request.document,
        )
    except VendorSchemaError as exc:
        raise HTTPException(status_code=502, detail="model_output_invalid_after_repair") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return VendorExtractionResponse(status="completed", result=result.as_dict())
