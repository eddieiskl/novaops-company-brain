from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya.retrieval import OpenSearchEvidenceRetriever
from maya.schemas import CallerContext, ContextPlan


class FakeIndices:
    def __init__(self) -> None:
        self.created = False

    def exists(self, index: str) -> bool:
        return False

    def create(self, index: str, body: dict) -> None:
        self.created = True


class FakeOpenSearchClient:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.indexed: list[dict] = []
        self.searches: list[dict] = []

    def index(self, index: str, id: str, body: dict) -> None:
        self.indexed.append({"index": index, "id": id, "body": body})

    def search(self, index: str, body: dict) -> dict:
        self.searches.append({"index": index, "body": body})
        return {
            "hits": {
                "hits": [
                    {
                        "_score": 10,
                        "_source": {
                            "source_path": "documents/employment/maya_cohen_offer_letter.md",
                            "chunk_id": "documents/employment/maya_cohen_offer_letter.md#chunk-1",
                            "collection": "employment",
                            "title": "Maya Cohen Offer Letter",
                            "text": "Maya Cohen starts 2026-08-01.",
                            "audience": "all",
                            "sensitivity": "restricted",
                            "subject_employee_id": "E001",
                            "update_date": None,
                        },
                    }
                ]
            }
        }


def test_opensearch_retriever_indexes_evidence_chunks() -> None:
    client = FakeOpenSearchClient()
    retriever = OpenSearchEvidenceRetriever(client)

    indexed = retriever.index_documents()

    assert indexed == len(retriever.chunks)
    assert client.indices.created
    assert any(item["id"] == "documents/employment/maya_cohen_offer_letter.md#chunk-1" for item in client.indexed)


def test_opensearch_query_has_hard_audience_and_subject_filters() -> None:
    retriever = OpenSearchEvidenceRetriever(FakeOpenSearchClient())
    caller = CallerContext("E004", "UG_HR")
    plan = ContextPlan(2, "offer_letter", required_evidence=("maya_cohen_offer_letter.md",))

    body = retriever.search_body("Maya offer letter", caller, plan, wide_limit=12)

    filters = body["query"]["bool"]["filter"]
    assert {"terms": {"audience": ["all", "manager"]}} in filters
    assert any(
        {"terms": {"subject_employee_id": ["E001"]}} in item["bool"]["should"]
        for item in filters
        if "bool" in item and "should" in item["bool"]
    )


def test_opensearch_denies_unauthorized_caller_before_search() -> None:
    client = FakeOpenSearchClient()
    retriever = OpenSearchEvidenceRetriever(client)
    caller = CallerContext("E009", "UG_REGULAR")
    plan = ContextPlan(2, "offer_letter", required_evidence=("maya_cohen_offer_letter.md",))

    chunks = retriever.retrieve("Maya offer letter", caller, plan)

    assert chunks == []
    assert client.searches == []
