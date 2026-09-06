from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain.runtime import build_company_brain_from_env
from company_brain.tools import RemoteMCPToolGateway
from maya.ports import BedrockAnswerPort


def test_runtime_selects_live_mcp_and_bedrock_without_calling_network(monkeypatch) -> None:
    monkeypatch.setenv("NOVAOPS_TOOL_MODE", "mcp")
    monkeypatch.setenv("NOVAOPS_MCP_URL", "http://127.0.0.1:19999/mcp")
    monkeypatch.setenv("NOVAOPS_ANSWER_MODE", "bedrock")

    agent = build_company_brain_from_env()

    assert isinstance(agent.tool_gateway, RemoteMCPToolGateway)
    assert isinstance(agent.maya.answer_port, BedrockAnswerPort)


def test_runtime_rejects_unknown_modes(monkeypatch) -> None:
    monkeypatch.setenv("NOVAOPS_TOOL_MODE", "local")
    monkeypatch.setenv("NOVAOPS_ANSWER_MODE", "mystery")

    try:
        build_company_brain_from_env()
    except ValueError as exc:
        assert "NOVAOPS_ANSWER_MODE" in str(exc)
    else:
        raise AssertionError("expected an invalid answer mode to fail")
