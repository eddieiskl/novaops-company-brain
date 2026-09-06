from __future__ import annotations

from dataclasses import dataclass
import os

from .graph import MayaAgent
from .ports import AnswerPort, BedrockAnswerPort, FakeWebexPort, Lesson9ApprovalWebexPort, WebexPort
from .retrieval import EvidenceRetriever, InMemoryEvidenceRetriever, OpenSearchEvidenceRetriever


RetrieverMode = str
AnswerMode = str
WebexMode = str


@dataclass(frozen=True)
class RetrieverStatus:
    mode: RetrieverMode
    available_modes: tuple[RetrieverMode, ...]
    detail: str
    answer_mode: AnswerMode
    answer_detail: str
    webex_mode: WebexMode
    webex_detail: str


def build_opensearch_retriever_from_env() -> OpenSearchEvidenceRetriever:
    url = os.getenv("MAYA_OPENSEARCH_URL")
    if not url:
        raise RuntimeError("Set MAYA_OPENSEARCH_URL before enabling OpenSearch retrieval.")

    try:
        from opensearchpy import OpenSearch
    except ImportError as exc:
        raise RuntimeError("Install opensearch-py before enabling OpenSearch retrieval.") from exc

    index = os.getenv("MAYA_OPENSEARCH_INDEX", "novaops-evidence")
    client = OpenSearch(hosts=[url])
    retriever = OpenSearchEvidenceRetriever(client, index_name=index, fallback=InMemoryEvidenceRetriever())
    if os.getenv("MAYA_OPENSEARCH_AUTO_INDEX", "1").strip().lower() not in {"0", "false", "no"}:
        retriever.index_documents()
    return retriever


class MayaRuntime:
    """Owns the active retriever mode and rebuilds the agent on mode changes."""

    available_modes: tuple[RetrieverMode, ...] = ("memory", "opensearch")
    available_answer_modes: tuple[AnswerMode, ...] = ("deterministic", "model")
    available_webex_modes: tuple[WebexMode, ...] = ("fake", "lesson9")

    def __init__(
        self,
        opensearch_factory=build_opensearch_retriever_from_env,
        answer_port_factory=None,
        webex_port_factory=None,
    ) -> None:
        self._opensearch_factory = opensearch_factory
        self._answer_port_factory = answer_port_factory or build_answer_port_from_env
        self._webex_port_factory = webex_port_factory or build_webex_port_from_env
        self.mode: RetrieverMode = os.getenv("MAYA_RETRIEVER", "memory").strip().lower() or "memory"
        self.answer_mode: AnswerMode = os.getenv("MAYA_ANSWER_MODE", "deterministic").strip().lower() or "deterministic"
        self.webex_mode: WebexMode = os.getenv("MAYA_WEBEX_PORT", "fake").strip().lower() or "fake"
        self.detail = "Using deterministic in-memory retrieval."
        self.answer_detail = "Using deterministic answer templates."
        self.webex_detail = "Using deterministic fake Webex handoff port."
        self.answer_port: AnswerPort | None = self._build_answer_port()
        self.webex_port: WebexPort = self._build_webex_port()
        self.retriever: EvidenceRetriever
        self.agent: MayaAgent
        try:
            self.set_mode(self.mode)
        except RuntimeError:
            self.mode = "memory"
            self.retriever = InMemoryEvidenceRetriever()
            self.agent = MayaAgent(self.retriever, self.webex_port, self.answer_port)

    def status(self) -> RetrieverStatus:
        return RetrieverStatus(
            self.mode,
            self.available_modes,
            self.detail,
            self.answer_mode,
            self.answer_detail,
            self.webex_mode,
            self.webex_detail,
        )

    def set_mode(self, mode: RetrieverMode) -> RetrieverStatus:
        normalized = mode.strip().lower()
        if normalized not in self.available_modes:
            raise ValueError(f"Unsupported retriever mode {mode!r}.")

        if normalized == "memory":
            self.retriever = InMemoryEvidenceRetriever()
            self.detail = "Using deterministic in-memory retrieval."
        else:
            self.retriever = self._opensearch_factory()
            self.detail = "Using OpenSearch retrieval adapter."

        self.mode = normalized
        self.agent = MayaAgent(self.retriever, self.webex_port, self.answer_port)
        return self.status()

    def _build_answer_port(self) -> AnswerPort | None:
        if self.answer_mode not in self.available_answer_modes:
            self.answer_mode = "deterministic"
            self.answer_detail = "Unsupported answer mode requested; using deterministic answer templates."
            return None
        if self.answer_mode == "deterministic":
            self.answer_detail = "Using deterministic answer templates."
            return None
        try:
            port = self._answer_port_factory()
        except RuntimeError as exc:
            self.answer_mode = "deterministic"
            self.answer_detail = f"Model answer mode unavailable: {exc}"
            return None
        self.answer_detail = "Using model-backed answers through Bedrock Converse (Nova 2 Lite)."
        return port

    def _build_webex_port(self) -> WebexPort:
        if self.webex_mode not in self.available_webex_modes:
            self.webex_mode = "fake"
            self.webex_detail = "Unsupported Webex mode requested; using fake handoff port."
            return FakeWebexPort()
        if self.webex_mode == "fake":
            self.webex_detail = "Using deterministic fake Webex handoff port."
            return FakeWebexPort()
        try:
            port = self._webex_port_factory()
        except RuntimeError as exc:
            self.webex_mode = "fake"
            self.webex_detail = f"Lesson 9 Webex approval port unavailable: {exc}"
            return FakeWebexPort()
        self.webex_detail = "Using Lesson 9 pending approval write boundary."
        return port


def build_answer_port_from_env() -> BedrockAnswerPort:
    return BedrockAnswerPort()


def build_webex_port_from_env() -> Lesson9ApprovalWebexPort:
    return Lesson9ApprovalWebexPort()
