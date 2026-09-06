from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_three_non_root_container_entry_points_have_health_checks() -> None:
    for name in ("Dockerfile.agent", "Dockerfile.mcp", "Dockerfile.renewal"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "USER novaops" in text
        assert "HEALTHCHECK" in text
        assert "AWS_ACCESS_KEY_ID" not in text
        assert "AWS_SECRET_ACCESS_KEY" not in text
        assert text.index("USER novaops") < text.index("CMD [")


def test_compose_has_request_tool_and_offline_planes_with_durable_state() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {"agent-api", "mcp", "renewal-worker"}
    assert services["agent-api"]["depends_on"]["mcp"]["condition"] == "service_healthy"
    assert services["agent-api"]["environment"]["NOVAOPS_MCP_URL"] == "http://mcp:9880/mcp"
    assert services["agent-api"]["ports"] == ["18080:8080"]
    assert all("novaops_state:/data" in service["volumes"] for service in services.values())
    assert all(service["image"].endswith(":${IMAGE_TAG:-dev}") for service in services.values())
    assert "novaops_state" in compose["volumes"]
