from __future__ import annotations

import os
import json
from typing import Any


class GatewayModelClient:
    """Provider-neutral application boundary. Retries belong to LiteLLM alone."""

    def __init__(self, *, client=None, max_tokens: int = 1200, temperature: float = 0.0):
        import httpx
        self.model_id = os.getenv("LITELLM_MODEL", "novaops-approved")
        self.region = "gateway"
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.last_usage: dict[str, int] = {}
        self.base_url = os.environ["LITELLM_BASE_URL"].rstrip("/")
        self.key = os.environ["LITELLM_API_KEY"]
        self.client = client or httpx.Client(timeout=60)

    def _complete(self, prompt: str, system: str, **kwargs) -> dict:
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        response = self.client.post(self.base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + self.key},
            json={"model": self.model_id, "messages": messages,
                  "max_tokens": self.max_tokens, "temperature": self.temperature, **kwargs})
        response.raise_for_status()
        result = response.json()
        usage = result.get("usage", {})
        self.last_usage = {k: v for k, v in usage.items() if isinstance(v, int) and not isinstance(v, bool)}
        return result["choices"][0]["message"]

    def generate(self, prompt: str, *, system: str = "") -> str:
        text = self._complete(prompt, system).get("content")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Gateway returned no text content.")
        return text.strip()

    def extract_with_tool(self, prompt: str, *, tool_name: str, input_schema: dict,
                          system: str = "") -> dict:
        message = self._complete(prompt, system,
            tools=[{"type": "function", "function": {"name": tool_name,
                "description": "Submit the structured extraction.", "parameters": input_schema}}],
            tool_choice={"type": "function", "function": {"name": tool_name}})
        for call in message.get("tool_calls", []):
            function = call.get("function", {})
            if function.get("name") == tool_name:
                value = json.loads(function["arguments"])
                if isinstance(value, dict):
                    return value
        raise RuntimeError("Gateway returned no matching structured tool input.")


def get_model(*, backend: str | None = None, **kwargs):
    selected = backend or os.getenv("NOVAOPS_MODEL_BACKEND") or (
        "gateway" if os.getenv("NOVAOPS_ANSWER_MODE") == "gateway" else "bedrock")
    if selected == "gateway":
        return GatewayModelClient(**kwargs)
    if selected == "bedrock":
        from bedrock_client import BedrockModelClient
        return BedrockModelClient(**kwargs)
    raise ValueError("NOVAOPS_MODEL_BACKEND must be bedrock or gateway.")


def __getattr__(name):
    # Preserve the original public import for local/direct-provider callers.
    if name in {"BedrockModelClient", "DEFAULT_NOVA_MODEL"}:
        import bedrock_client
        return getattr(bedrock_client, name)
    raise AttributeError(name)
