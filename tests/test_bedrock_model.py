from __future__ import annotations

import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_client import BedrockModelClient, DEFAULT_NOVA_MODEL
from maya.ports import BedrockAnswerPort


class FakeBedrockRuntime:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def converse(self, **kwargs) -> dict:
        self.requests.append(kwargs)
        return {"output": {"message": {"content": [{"text": "Grounded answer [source]."}]}}}


def test_model_boundary_uses_nova_2_lite_converse() -> None:
    client = FakeBedrockRuntime()
    model = BedrockModelClient(client=client)

    answer = model.generate("Evidence here", system="Use evidence only")

    assert answer == "Grounded answer [source]."
    assert client.requests[0]["modelId"] == DEFAULT_NOVA_MODEL
    assert client.requests[0]["messages"][0]["content"][0]["text"] == "Evidence here"
    assert client.requests[0]["system"][0]["text"] == "Use evidence only"


def test_bedrock_answer_port_keeps_provider_call_out_of_agent_graph() -> None:
    client = FakeBedrockRuntime()
    port = BedrockAnswerPort(BedrockModelClient(client=client))

    answer = asyncio.run(port.answer("Answer with citations."))

    assert answer == "Grounded answer [source]."
    assert "never claim an action happened" in client.requests[0]["system"][0]["text"]
