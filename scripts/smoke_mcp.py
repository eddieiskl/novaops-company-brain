from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from company_brain import build_company_brain_from_env
from company_brain.mcp_client import MCPToolClient
from maya import CallerContext


def main() -> int:
    url = os.getenv("NOVAOPS_MCP_URL", "http://127.0.0.1:9880/mcp")
    tools = MCPToolClient(url).discover_sync()
    names = {tool["name"] for tool in tools}
    required = {
        "retrieve_evidence",
        "get_employee",
        "check_software_subscription",
        "inspect_software_seat_assignments",
        "prepare_access_handoff",
        "resume_access_handoff",
    }
    missing = sorted(required - names)
    if missing:
        print(f"MCP smoke failed; missing tools: {', '.join(missing)}")
        return 1

    os.environ["NOVAOPS_TOOL_MODE"] = "mcp"
    agent = build_company_brain_from_env()
    result = agent.handle_turn(
        "mcp-smoke",
        CallerContext("E010", "UG_REGULAR"),
        "Can I use my personal laptop for work?",
        request_id="mcp-smoke-001",
    )
    if result.status != "completed" or "equipment_policy.md" not in result.answer:
        print(f"MCP smoke failed; unexpected result: {result}")
        return 1
    print(f"MCP smoke passed: {len(tools)} tools discovered; {result.intent} completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
