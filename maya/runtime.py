from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .graph import MayaAgent
from .ports import AnswerPort, BedrockAnswerPort, FakeWebexPort, Lesson9ApprovalWebexPort, WebexPort
from .retrieval import EvidenceRetriever, InMemoryEvidenceRetriever, OpenSearchEvidenceRetriever
from .retrieval_security import (
    BedrockRetrievalGuard,
    GuardedEvidenceRetriever,
    QuarantineRegistry,
    TrustedCorpusManifest,
)


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
    retrieval_security_mode: str
    retrieval_security_detail: str


def build_opensearch_client_from_env():
    try:
        from opensearchpy import OpenSearch
    except ImportError as exc:
        raise RuntimeError("Install opensearch-py before enabling OpenSearch retrieval.") from exc

    maya_url = os.getenv("MAYA_OPENSEARCH_URL")
    url = maya_url or os.getenv("OPENSEARCH_ENDPOINT")
    collection = os.getenv("MAYA_OPENSEARCH_COLLECTION") or os.getenv("OPENSEARCH_COLLECTION")
    region = os.getenv("AWS_REGION", "us-east-1")
    service = os.getenv("MAYA_OPENSEARCH_SERVICE", "aoss" if collection and not maya_url else "").strip()

    session = None
    if not url and collection:
        import boto3

        key = os.getenv("OPENSEARCH_AWS_ACCESS_KEY_ID")
        secret = os.getenv("OPENSEARCH_AWS_SECRET_ACCESS_KEY")
        session = boto3.Session(
            aws_access_key_id=key or None,
            aws_secret_access_key=secret or None,
            region_name=region,
        )
        details = session.client("opensearchserverless").batch_get_collection(
            names=[collection]
        ).get("collectionDetails", [])
        if not details or not details[0].get("collectionEndpoint"):
            raise RuntimeError(f"OpenSearch collection {collection!r} is unavailable.")
        url = details[0]["collectionEndpoint"]

    if not url:
        raise RuntimeError(
            "Set MAYA_OPENSEARCH_URL or MAYA_OPENSEARCH_COLLECTION before enabling OpenSearch retrieval."
        )

    if not service:
        return OpenSearch(hosts=[url])

    import boto3
    from opensearchpy import AWSV4SignerAuth, RequestsHttpConnection

    if session is None:
        key = os.getenv("OPENSEARCH_AWS_ACCESS_KEY_ID")
        secret = os.getenv("OPENSEARCH_AWS_SECRET_ACCESS_KEY")
        session = boto3.Session(
            aws_access_key_id=key or None,
            aws_secret_access_key=secret or None,
            region_name=region,
        )
    host = url.replace("https://", "").replace("http://", "").rstrip("/")
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=AWSV4SignerAuth(session.get_credentials(), region, service),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=120,
        max_retries=3,
        retry_on_timeout=True,
    )


def build_opensearch_retriever_from_env() -> OpenSearchEvidenceRetriever:
    client = build_opensearch_client_from_env()

    index = os.getenv("MAYA_OPENSEARCH_INDEX", "novaops-evidence")
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
        self.retrieval_security_mode = (
            os.getenv("MAYA_RETRIEVAL_SECURITY", "provenance").strip().lower() or "provenance"
        )
        self.detail = "Using deterministic in-memory retrieval."
        self.answer_detail = "Using deterministic answer templates."
        self.webex_detail = "Using deterministic fake Webex handoff port."
        self.retrieval_security_detail = "Application-owned source manifest is enforced."
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
            self.retrieval_security_mode,
            self.retrieval_security_detail,
        )

    def set_mode(self, mode: RetrieverMode) -> RetrieverStatus:
        normalized = mode.strip().lower()
        if normalized not in self.available_modes:
            raise ValueError(f"Unsupported retriever mode {mode!r}.")

        if normalized == "memory":
            base_retriever = InMemoryEvidenceRetriever()
            self.detail = "Using deterministic in-memory retrieval."
        else:
            base_retriever = self._opensearch_factory()
            self.detail = "Using OpenSearch retrieval adapter."

        self.retriever = self._secure_retriever(base_retriever)
        self.mode = normalized
        self.agent = MayaAgent(self.retriever, self.webex_port, self.answer_port)
        return self.status()

    def _secure_retriever(self, retriever: EvidenceRetriever) -> EvidenceRetriever:
        mode = self.retrieval_security_mode
        if mode not in {"off", "provenance", "semantic"}:
            mode = "provenance"
            self.retrieval_security_mode = mode
        if mode == "off":
            self.retrieval_security_detail = "Retrieval security is disabled for boundary testing."
            return retriever

        chunks = list(getattr(retriever, "chunks", []))
        if not chunks:
            raise RuntimeError("A trusted local corpus is required for secured retrieval.")
        manifest = TrustedCorpusManifest.from_chunks(chunks)
        quarantine_path = Path(
            os.getenv(
                "MAYA_RETRIEVAL_QUARANTINE",
                str(Path(__file__).resolve().parents[1] / ".state" / "retrieval-quarantine.json"),
            )
        )
        semantic_guard = BedrockRetrievalGuard() if mode == "semantic" else None
        self.retrieval_security_detail = (
            "Source manifest and semantic retrieval guard are enforced."
            if semantic_guard is not None
            else "Application-owned source manifest is enforced."
        )
        return GuardedEvidenceRetriever(
            retriever,
            QuarantineRegistry(quarantine_path),
            semantic_guard,
            trusted_corpus=manifest,
            audit_path=Path(__file__).resolve().parents[1] / ".state" / "retrieval-rejections.jsonl",
        )

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
