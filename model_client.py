from __future__ import annotations

import os
from typing import Any


DEFAULT_NOVA_MODEL = "us.amazon.nova-2-lite-v1:0"


class BedrockModelClient:
    """The one provider boundary used for NovaOps model calls."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model_id: str | None = None,
        region: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> None:
        self._client = client
        self.model_id = model_id or os.getenv("NOVAOPS_BEDROCK_MODEL", DEFAULT_NOVA_MODEL)
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.last_usage: dict[str, int] = {}

    @property
    def client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def generate(self, prompt: str, *, system: str = "") -> str:
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
                "topP": 0.9,
            },
        }
        if system:
            request["system"] = [{"text": system}]
        response = self.client.converse(**request)
        self._capture_usage(response)
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block.get("text", "") for block in blocks if isinstance(block, dict)).strip()
        if not text:
            raise RuntimeError("Bedrock returned no text content.")
        return text

    def extract_with_tool(
        self,
        prompt: str,
        *,
        tool_name: str,
        input_schema: dict[str, Any],
        system: str = "",
    ) -> dict[str, Any]:
        """Make one forced-tool Converse call and return its structured input."""

        request: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
                "topP": 0.9,
            },
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool_name,
                            "description": "Submit the validated structured extraction.",
                            "inputSchema": {"json": input_schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": tool_name}},
            },
        }
        if system:
            request["system"] = [{"text": system}]
        response = self.client.converse(**request)
        self._capture_usage(response)
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        for block in blocks:
            tool_use = block.get("toolUse") if isinstance(block, dict) else None
            if tool_use and tool_use.get("name") == tool_name and isinstance(tool_use.get("input"), dict):
                return tool_use["input"]
        raise RuntimeError(f"Bedrock returned no forced {tool_name!r} tool input.")

    def _capture_usage(self, response: dict[str, Any]) -> None:
        usage = response.get("usage", {})
        self.last_usage = {
            str(key): int(value)
            for key, value in usage.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
