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


def test_cloud_compose_uses_external_state_and_hardened_non_root_services() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.cloud.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {"state-init", "agent-api", "mcp", "renewal-worker"}
    assert services["state-init"]["user"] == "0:0"
    for name in ("agent-api", "mcp", "renewal-worker"):
        service = services[name]
        assert service["read_only"] is True
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["volumes"][0]["source"] == "/srv/novaops/state"
        assert "AWS_ACCESS_KEY_ID" not in service.get("environment", {})
        assert "AWS_SECRET_ACCESS_KEY" not in service.get("environment", {})
    assert services["agent-api"]["environment"]["NOVAOPS_RELEASE_SHA"].startswith("${")


def test_cloudformation_is_cost_scoped_and_credential_bounded() -> None:
    template = (ROOT / "deploy" / "aws" / "cloudformation.yaml").read_text(encoding="utf-8")
    assert "t3.small" in template
    assert "AWS::EFS::FileSystem" in template
    assert "Encrypted: true" in template
    assert "HttpTokens: required" in template
    assert "GitCommit" in template
    assert "AWS_ACCESS_KEY_ID" not in template
    assert "AWS_SECRET_ACCESS_KEY" not in template


def test_cloud_deployer_requires_explicit_cost_flag_and_release_is_verified() -> None:
    deploy = (ROOT / "deploy" / "aws" / "deploy.sh").read_text(encoding="utf-8")
    verify = (ROOT / "deploy" / "aws" / "verify.sh").read_text(encoding="utf-8")
    assert "--approve-costs" in deploy
    assert "git merge-base --is-ancestor" in deploy
    assert "/health/live" in verify
    assert "/health/ready" in verify
    assert "/health/version" in verify
