from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
from typing import Protocol

from . import ops
from .schemas import CallerContext, ContextPlan, EvidenceChunk


class PermissionDenied(Exception):
    pass


class EvidenceRetriever(Protocol):
    def assert_authorized(self, caller: CallerContext, subject_employee_id: str) -> None:
        ...

    def retrieve(self, query: str, caller: CallerContext, plan: ContextPlan, limit: int = 6) -> list[EvidenceChunk]:
        ...


class InMemoryEvidenceRetriever:
    """OpenSearch-shaped retriever with hard caller filtering before scoring."""

    def __init__(self, dataset_root: Path | None = None) -> None:
        self.dataset_root = dataset_root or self.default_dataset_root()
        self.chunks = self._load_chunks()

    @staticmethod
    def default_dataset_root() -> Path:
        configured = os.getenv("MAYA_DATASET_ROOT")
        if configured:
            return Path(configured).expanduser().resolve()
        return Path(__file__).resolve().parents[1] / "novaops-enterprise-agent-dataset"

    def retrieve(self, query: str, caller: CallerContext, plan: ContextPlan, limit: int = 6) -> list[EvidenceChunk]:
        try:
            self.assert_authorized(caller, plan.subject_employee_id)
        except PermissionDenied:
            return []
        allowed = [chunk for chunk in self.chunks if self._is_allowed(chunk, caller, plan)]
        query_terms = self._terms(" ".join((query, plan.intent, " ".join(plan.required_evidence))))
        scored: list[EvidenceChunk] = []
        for chunk in allowed:
            score = self._score(query_terms, chunk, plan)
            if score > 0:
                scored.append(EvidenceChunk(**{**chunk.__dict__, "score": score}))
        scored.sort(key=lambda c: (c.score, self._specificity(c)), reverse=True)
        return self._select_diverse(scored, limit)

    def assert_authorized(self, caller: CallerContext, subject_employee_id: str) -> None:
        if caller.user_group in {"UG_HR", "UG_IT"}:
            return
        if caller.employee_id == subject_employee_id:
            return
        raise PermissionDenied("Caller is not authorized to retrieve the requested restricted evidence.")

    def _is_allowed(self, chunk: EvidenceChunk, caller: CallerContext, plan: ContextPlan) -> bool:
        if chunk.subject_employee_id:
            try:
                self.assert_authorized(caller, chunk.subject_employee_id)
            except PermissionDenied:
                return False
        if chunk.audience == "hr" and caller.user_group != "UG_HR":
            return False
        if chunk.audience == "it_hr" and caller.user_group not in {"UG_HR", "UG_IT"}:
            return False
        if chunk.audience == "manager" and not ops.is_manager(caller.employee_id):
            return False
        return True

    def _load_chunks(self) -> list[EvidenceChunk]:
        chunks: list[EvidenceChunk] = []
        documents_root = self.dataset_root / "documents"
        if not documents_root.exists():
            documents_root = self.dataset_root
        for collection_dir in sorted(path for path in documents_root.iterdir() if path.is_dir()):
            collection = collection_dir.name
            for path in sorted(collection_dir.glob("*.md")):
                raw = path.read_text(encoding="utf-8")
                metadata, text = self._parse_front_matter(raw)
                chunks.extend(self._chunks_for(path, collection, text, metadata))
        return chunks

    def _chunks_for(
        self,
        path: Path,
        collection: str,
        text: str,
        metadata: dict[str, str],
    ) -> list[EvidenceChunk]:
        source_path = f"documents/{collection}/{path.name}"
        subject = self._subject_for(path.name) if collection == "employment" else None
        audience = metadata.get("audience", "all").strip().lower() or "all"
        sensitivity = "restricted" if audience == "manager" or subject else "internal"
        sections = self._split_sections(text)
        chunks: list[EvidenceChunk] = []
        for index, (title, body) in enumerate(sections, start=1):
            chunks.append(
                EvidenceChunk(
                    source_path=source_path,
                    chunk_id=f"{source_path}#chunk-{index}",
                    collection=collection,
                    title=title,
                    text=body,
                    audience=audience,
                    sensitivity=sensitivity,
                    subject_employee_id=subject,
                    update_date=metadata.get("last_updated") or metadata.get("effective_date"),
                )
            )
        return chunks

    def _subject_for(self, filename: str) -> str | None:
        seed_path = self.dataset_root / "database" / "seed.json"
        if not seed_path.exists():
            return "E001" if "maya_cohen" in filename else "E010" if "rachel_stein" in filename else None
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        for employee in data.get("employees", []):
            slug = re.sub(r"[^a-z0-9]+", "_", employee["full_name"].lower()).strip("_")
            if filename.startswith(f"{slug}_"):
                return employee["employee_id"]
        return None

    @staticmethod
    def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
        if not raw.startswith("---\n"):
            return {}, raw
        end = raw.find("\n---\n", 4)
        if end < 0:
            return {}, raw
        metadata: dict[str, str] = {}
        for line in raw[4:end].splitlines():
            key, separator, value = line.partition(":")
            if separator:
                metadata[key.strip()] = value.strip()
        return metadata, raw[end + 5 :].lstrip()

    @staticmethod
    def _split_sections(text: str, max_chars: int = 2800) -> list[tuple[str, str]]:
        lines = text.splitlines()
        document_title = next((line.lstrip("# ").strip() for line in lines if line.startswith("# ")), "Document")
        sections: list[tuple[str, str]] = []
        title = document_title
        buffer: list[str] = []

        def flush() -> None:
            nonlocal buffer
            body = "\n".join(buffer).strip()
            if not body:
                buffer = []
                return
            paragraphs = body.split("\n\n")
            current = ""
            for paragraph in paragraphs:
                candidate = f"{current}\n\n{paragraph}".strip()
                if current and len(candidate) > max_chars:
                    sections.append((title, current))
                    current = paragraph
                else:
                    current = candidate
            if current:
                sections.append((title, current))
            buffer = []

        for line in lines:
            if line.startswith("## "):
                flush()
                title = line[3:].strip()
            else:
                buffer.append(line)
        flush()
        return sections or [(document_title, text)]

    @staticmethod
    def _select_diverse(scored: list[EvidenceChunk], limit: int) -> list[EvidenceChunk]:
        selected: list[EvidenceChunk] = []
        seen_sources: set[str] = set()
        for chunk in scored:
            if chunk.source_path not in seen_sources:
                selected.append(chunk)
                seen_sources.add(chunk.source_path)
                if len(selected) == limit:
                    return selected
        for chunk in scored:
            if chunk not in selected:
                selected.append(chunk)
                if len(selected) == limit:
                    break
        return selected

    def _score(self, query_terms: set[str], chunk: EvidenceChunk, plan: ContextPlan) -> float:
        haystack = self._terms(" ".join((chunk.title, chunk.text, chunk.source_path)))
        score = len(query_terms & haystack)
        for required in plan.required_evidence:
            if required in chunk.source_path:
                score += 20
        if plan.subject_employee_id and chunk.subject_employee_id == plan.subject_employee_id:
            score += 8
        return float(score)

    @staticmethod
    def _specificity(chunk: EvidenceChunk) -> int:
        return 1 if chunk.subject_employee_id else 0

    @staticmethod
    def _terms(text: str) -> set[str]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
        return {term for term in cleaned.split() if len(term) > 2}


class OpenSearchEvidenceRetriever(InMemoryEvidenceRetriever):
    """OpenSearch-backed retriever with the same authorization contract.

    The class accepts an already-configured OpenSearch-compatible client so AWS,
    auth, retry, and network choices stay outside the agent graph. If a local run does
    not provide a client, callers can use the inherited in-memory implementation.
    """

    def __init__(
        self,
        client,
        index_name: str = "novaops-evidence",
        dataset_root: Path | None = None,
        fallback: InMemoryEvidenceRetriever | None = None,
    ) -> None:
        super().__init__(dataset_root)
        self.client = client
        self.index_name = index_name
        self.fallback = fallback

    def index_documents(self) -> int:
        """Create/update the evidence index from the configured NovaOps dataset."""
        if hasattr(self.client, "indices"):
            exists = self.client.indices.exists(index=self.index_name)
            if not exists:
                self.client.indices.create(index=self.index_name, body=self.index_mapping())

        for chunk in self.chunks:
            self.client.index(
                index=self.index_name,
                id=chunk.chunk_id,
                body=asdict(chunk),
            )
        return len(self.chunks)

    def retrieve(self, query: str, caller: CallerContext, plan: ContextPlan, limit: int = 6) -> list[EvidenceChunk]:
        try:
            self.assert_authorized(caller, plan.subject_employee_id)
        except PermissionDenied:
            return []

        body = self.search_body(query, caller, plan, wide_limit=max(limit * 4, 12))
        try:
            response = self.client.search(index=self.index_name, body=body)
        except Exception:
            if self.fallback is None:
                raise
            return self.fallback.retrieve(query, caller, plan, limit)

        hits = response.get("hits", {}).get("hits", [])
        chunks = [self._chunk_from_hit(hit) for hit in hits]
        chunks.sort(key=lambda chunk: (chunk.score, self._specificity(chunk)), reverse=True)
        return self._select_diverse(chunks, limit)

    def search_body(self, query: str, caller: CallerContext, plan: ContextPlan, wide_limit: int) -> dict:
        """Build the hard-filtered OpenSearch query used before any ranking."""
        terms = " ".join((query, plan.intent, " ".join(plan.required_evidence))).strip()
        filters: list[dict] = [
            {"terms": {"audience": self._allowed_audiences(caller)}},
            self._subject_filter(caller, plan),
        ]

        return {
            "size": wide_limit,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": terms,
                                "fields": ["title^3", "text", "source_path^2", "collection"],
                                "operator": "or",
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
        }

    @staticmethod
    def index_mapping() -> dict:
        return {
            "mappings": {
                "properties": {
                    "source_path": {"type": "keyword"},
                    "chunk_id": {"type": "keyword"},
                    "collection": {"type": "keyword"},
                    "title": {"type": "text"},
                    "text": {"type": "text"},
                    "audience": {"type": "keyword"},
                    "sensitivity": {"type": "keyword"},
                    "subject_employee_id": {"type": "keyword"},
                    "update_date": {"type": "date", "ignore_malformed": True},
                }
            }
        }

    @staticmethod
    def _allowed_audiences(caller: CallerContext) -> list[str]:
        audiences = ["all"]
        if ops.is_manager(caller.employee_id):
            audiences.append("manager")
        return audiences

    @staticmethod
    def _subject_filter(caller: CallerContext, plan: ContextPlan) -> dict:
        allowed_subjects = [plan.subject_employee_id]
        if caller.user_group == "UG_REGULAR":
            allowed_subjects = [caller.employee_id]
        return {
            "bool": {
                "should": [
                    {"bool": {"must_not": {"exists": {"field": "subject_employee_id"}}}},
                    {"terms": {"subject_employee_id": allowed_subjects}},
                ],
                "minimum_should_match": 1,
            }
        }

    @staticmethod
    def _chunk_from_hit(hit: dict) -> EvidenceChunk:
        source = hit.get("_source", {})
        return EvidenceChunk(
            source_path=source["source_path"],
            chunk_id=source["chunk_id"],
            collection=source["collection"],
            title=source["title"],
            text=source["text"],
            audience=source["audience"],
            sensitivity=source["sensitivity"],
            subject_employee_id=source.get("subject_employee_id"),
            update_date=source.get("update_date"),
            score=float(hit.get("_score") or source.get("score") or 0.0),
        )
