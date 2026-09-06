from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dev_opensearch_server import DevOpenSearchStore
from maya.runtime import build_opensearch_retriever_from_env


class FakeIndices:
    def __init__(self) -> None:
        self.created = False

    def exists(self, index: str) -> bool:
        return False

    def create(self, index: str, body: dict) -> None:
        self.created = True


class FakeOpenSearchClient:
    def __init__(self, hosts: list[str]) -> None:
        self.hosts = hosts
        self.indices = FakeIndices()
        self.indexed: list[dict] = []

    def index(self, index: str, id: str, body: dict) -> None:
        self.indexed.append({"index": index, "id": id, "body": body})


def test_dev_store_applies_audience_and_subject_filters() -> None:
    store = DevOpenSearchStore()
    store.create_index("maya", {})
    store.index_document(
        "maya",
        "public",
        {
            "source_path": "policies/onboarding_policy.md",
            "chunk_id": "public",
            "collection": "policies",
            "title": "Onboarding Policy",
            "text": "Day-one onboarding requires MFA.",
            "audience": "all",
            "subject_employee_id": None,
        },
    )
    store.index_document(
        "maya",
        "restricted",
        {
            "source_path": "documents/employment/maya_cohen_offer_letter.md",
            "chunk_id": "restricted",
            "collection": "employment",
            "title": "Maya Cohen Offer Letter",
            "text": "Maya Cohen needs Slack and Webex.",
            "audience": "all",
            "subject_employee_id": "E001",
        },
    )

    response = store.search(
        "maya",
        {
            "size": 10,
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": "onboarding Maya offer", "fields": ["title", "text"]}}],
                    "filter": [
                        {"terms": {"audience": ["all"]}},
                        {
                            "bool": {
                                "should": [
                                    {"bool": {"must_not": {"exists": {"field": "subject_employee_id"}}}},
                                    {"terms": {"subject_employee_id": ["E009"]}},
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                    ],
                }
            },
        },
    )

    assert [hit["_id"] for hit in response["hits"]["hits"]] == ["public"]


def test_runtime_builder_auto_indexes_when_url_is_configured(monkeypatch) -> None:
    clients: list[FakeOpenSearchClient] = []

    def fake_opensearch(hosts: list[str]) -> FakeOpenSearchClient:
        client = FakeOpenSearchClient(hosts)
        clients.append(client)
        return client

    monkeypatch.setitem(sys.modules, "opensearchpy", SimpleNamespace(OpenSearch=fake_opensearch))
    monkeypatch.setenv("MAYA_OPENSEARCH_URL", "http://127.0.0.1:9200")
    monkeypatch.delenv("MAYA_OPENSEARCH_AUTO_INDEX", raising=False)

    retriever = build_opensearch_retriever_from_env()

    assert retriever.index_name == "novaops-evidence"
    assert clients[0].hosts == ["http://127.0.0.1:9200"]
    assert clients[0].indices.created
    assert any(item["id"] == "documents/employment/maya_cohen_offer_letter.md#chunk-1" for item in clients[0].indexed)
