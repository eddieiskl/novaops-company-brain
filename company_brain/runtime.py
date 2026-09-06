from __future__ import annotations

import os

from maya.ports import BedrockAnswerPort

from .agent import CompanyBrainAgent
from .tools import LocalToolGateway, RemoteMCPToolGateway


def build_company_brain_from_env() -> CompanyBrainAgent:
    """Build the same core agent with a test-local or live MCP tool boundary."""
    mode = os.getenv("NOVAOPS_TOOL_MODE", "local").strip().lower()
    answer_mode = os.getenv("NOVAOPS_ANSWER_MODE", "deterministic").strip().lower()
    answer_port = BedrockAnswerPort() if answer_mode == "bedrock" else None
    if answer_mode not in {"deterministic", "bedrock"}:
        raise ValueError("NOVAOPS_ANSWER_MODE must be 'deterministic' or 'bedrock'.")
    if mode == "local":
        return CompanyBrainAgent(LocalToolGateway(), answer_port=answer_port)
    if mode == "mcp":
        url = os.getenv("NOVAOPS_MCP_URL", "http://127.0.0.1:9880/mcp")
        return CompanyBrainAgent(RemoteMCPToolGateway(url), answer_port=answer_port)
    raise ValueError("NOVAOPS_TOOL_MODE must be 'local' or 'mcp'.")
