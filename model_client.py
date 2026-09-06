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
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block.get("text", "") for block in blocks if isinstance(block, dict)).strip()
        if not text:
            raise RuntimeError("Bedrock returned no text content.")
        return text
