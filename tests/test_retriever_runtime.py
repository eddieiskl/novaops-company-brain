from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import CallerContext
from maya.retrieval import InMemoryEvidenceRetriever
from maya.runtime import MayaRuntime, build_opensearch_retriever_from_env


class FakeAnswerPort:
    async def answer(self, prompt: str) -> str:
        assert "Deterministic fallback answer" in prompt
        return "MODEL ANSWER"


def test_retriever_runtime_defaults_to_memory(monkeypatch) -> None:
    monkeypatch.delenv("MAYA_RETRIEVER", raising=False)
    monkeypatch.delenv("MAYA_ANSWER_MODE", raising=False)
    monkeypatch.delenv("MAYA_WEBEX_PORT", raising=False)
    runtime = MayaRuntime()

    status = runtime.status()

    assert status.mode == "memory"
    assert status.answer_mode == "deterministic"
    assert status.webex_mode == "fake"
    assert "in-memory" in status.detail


def test_retriever_runtime_can_toggle_opensearch_with_factory() -> None:
    runtime = MayaRuntime(opensearch_factory=InMemoryEvidenceRetriever)

    enabled = runtime.set_mode("opensearch")
    disabled = runtime.set_mode("memory")

    assert enabled.mode == "opensearch"
    assert disabled.mode == "memory"
    assert runtime.agent is not None


def test_env_opensearch_builder_requires_url(monkeypatch) -> None:
    monkeypatch.delenv("MAYA_OPENSEARCH_URL", raising=False)

    try:
        build_opensearch_retriever_from_env()
    except RuntimeError as exc:
        assert "MAYA_OPENSEARCH_URL" in str(exc)
    else:
        raise AssertionError("expected missing OpenSearch URL to fail")


def test_runtime_model_answer_mode_uses_injected_answer_port(monkeypatch) -> None:
    monkeypatch.setenv("MAYA_ANSWER_MODE", "model")
    runtime = MayaRuntime(answer_port_factory=lambda: FakeAnswerPort())
    result = runtime.agent.handle_turn_sync(
        "answer-mode-thread",
        caller=CallerContext("E004", "UG_HR"),
        turn=1,
        user_text="Pull up her employee record.",
    )

    assert runtime.status().answer_mode == "model"
    assert result.answer == "MODEL ANSWER"


def test_runtime_model_answer_mode_uses_lazy_bedrock_configuration(monkeypatch) -> None:
    monkeypatch.setenv("MAYA_ANSWER_MODE", "model")
    monkeypatch.delenv("NOVAOPS_BEDROCK_MODEL", raising=False)
    runtime = MayaRuntime()

    assert runtime.status().answer_mode == "model"
    assert "Bedrock Converse" in runtime.status().answer_detail
