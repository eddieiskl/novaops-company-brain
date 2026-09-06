from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from company_brain import build_company_brain_from_env
from company_brain.mcp_client import MCPToolClient
from maya import CallerContext, ops
from vendor.runtime import build_vendor_extractor_from_env


ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="NovaOps Company Brain", version="0.1.0")
_agent = None
_agent_lock = Lock()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    workflow_scope: Literal["maya_hr", "webex_ops"]
    intent: str
    status: Literal["completed", "blocked", "pending", "needs_human", "failed"]
    answer: str
    tool_sequence: list[str]
    citations: list[str]


class VendorExtractionRequest(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    source_type: Literal["formal_document", "email_chain", "call_transcript"]
    document: str = Field(min_length=1, max_length=100_000)


class VendorExtractionResponse(StrictModel):
    status: Literal["completed"]
    result: dict[str, Any]


def _company_brain():
    global _agent
    if _agent is None:
        _agent = build_company_brain_from_env()
    return _agent


@app.get("/health/live")
def liveness() -> dict[str, str]:
    """Process-only health check; never calls a model or dependency."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, Any]:
    """Check local data and the selected tool boundary, without a model call."""
    schema = ROOT / "novaops-enterprise-agent-dataset" / "database" / "schema.sql"
    if not schema.is_file():
        raise HTTPException(status_code=503, detail="dataset unavailable")
    mode = os.getenv("NOVAOPS_TOOL_MODE", "local").strip().lower()
    try:
        if mode == "mcp":
            url = os.getenv("NOVAOPS_MCP_URL", "http://127.0.0.1:9880/mcp")
            discovered = MCPToolClient(url).discover_sync()
            if not discovered:
                raise RuntimeError("MCP exposed no tools")
        else:
            ops.conn().execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"tool dependency unavailable: {type(exc).__name__}") from exc
    return {"status": "ready", "tool_mode": mode}


@app.post("/v1/agent/turn", response_model=AgentTurnResponse)
def agent_turn(request: AgentTurnRequest) -> AgentTurnResponse:
    with _agent_lock:
        result = _company_brain().handle_turn(
            request.thread_id,
            CallerContext(request.caller.employee_id, request.caller.user_group),
            request.message,
            turn=request.turn,
            request_id=request.request_id,
        )
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


@app.post("/v1/vendor/extract", response_model=VendorExtractionResponse)
def vendor_extract(request: VendorExtractionRequest) -> VendorExtractionResponse:
    try:
        result = build_vendor_extractor_from_env().extract(
            request.source_id,
            request.source_type,
            request.document,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return VendorExtractionResponse(status="completed", result=result.as_dict())
