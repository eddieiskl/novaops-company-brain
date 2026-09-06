from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse


class DevOpenSearchStore:
    """Tiny OpenSearch-compatible store for the Maya evidence demo."""

    def __init__(self) -> None:
        self.indices: dict[str, dict[str, dict[str, Any]]] = {}
        self.mappings: dict[str, dict[str, Any]] = {}

    def index_exists(self, index: str) -> bool:
        return index in self.indices

    def create_index(self, index: str, body: dict[str, Any]) -> None:
        self.indices.setdefault(index, {})
        self.mappings[index] = body

    def index_document(self, index: str, doc_id: str, body: dict[str, Any]) -> None:
        self.indices.setdefault(index, {})[doc_id] = body

    def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        docs = self.indices.get(index, {})
        query = body.get("query", {}).get("bool", {})
        filters = query.get("filter", [])
        terms = self._query_terms(query)
        size = int(body.get("size") or 10)
        hits = []

        for doc_id, doc in docs.items():
            if not all(self._matches_filter(doc, item) for item in filters):
                continue
            score = self._score(doc, terms)
            if score <= 0:
                continue
            hits.append({"_id": doc_id, "_index": index, "_score": score, "_source": doc})

        hits.sort(key=lambda hit: hit["_score"], reverse=True)
        return {"hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits[:size]}}

    @staticmethod
    def _query_terms(query: dict[str, Any]) -> set[str]:
        text = " ".join(
            str(item.get("multi_match", {}).get("query", ""))
            for item in query.get("must", [])
            if isinstance(item, dict)
        )
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
        return {term for term in cleaned.split() if len(term) > 2}

    @classmethod
    def _matches_filter(cls, doc: dict[str, Any], item: dict[str, Any]) -> bool:
        if "terms" in item:
            field, values = next(iter(item["terms"].items()))
            return doc.get(cls._field(field)) in set(values)
        if "term" in item:
            field, value = next(iter(item["term"].items()))
            return doc.get(cls._field(field)) == value
        if "exists" in item:
            field = cls._field(item["exists"]["field"])
            return doc.get(field) not in (None, "")
        if "bool" in item:
            rules = item["bool"]
            if "must_not" in rules:
                return not cls._matches_filter(doc, rules["must_not"])
            if "filter" in rules:
                filters = rules["filter"]
                if isinstance(filters, dict):
                    filters = [filters]
                return all(cls._matches_filter(doc, rule) for rule in filters)
            if "should" in rules:
                minimum = int(rules.get("minimum_should_match", 1))
                if minimum == 0:
                    return True
                return sum(1 for rule in rules["should"] if cls._matches_filter(doc, rule)) >= minimum
        return True

    @staticmethod
    def _field(field: str) -> str:
        return field.removesuffix(".keyword")

    @staticmethod
    def _score(doc: dict[str, Any], terms: set[str]) -> float:
        if not terms:
            return 1.0
        fields = {
            "title": 3.0,
            "source_path": 2.0,
            "collection": 1.5,
            "text": 1.0,
        }
        score = 0.0
        for field, weight in fields.items():
            value = str(doc.get(field, "")).lower()
            score += sum(weight for term in terms if term in value)
        return score


def handler_for(store: DevOpenSearchStore):
    class DevOpenSearchHandler(BaseHTTPRequestHandler):
        server_version = "MayaDevOpenSearch/1.0"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", ""}:
                self._send_json({"name": "maya-dev-opensearch", "version": {"distribution": "opensearch"}})
                return
            if path == "/_cluster/health":
                self._send_json({"status": "green", "number_of_nodes": 1})
                return
            self.send_error(404, "Not found")

        def do_HEAD(self) -> None:
            parts = self._path_parts()
            if len(parts) == 1 and store.index_exists(parts[0]):
                self._send_empty(200)
                return
            self._send_empty(404)

        def do_PUT(self) -> None:
            self._handle_write()

        def do_POST(self) -> None:
            parts = self._path_parts()
            if len(parts) == 2 and parts[1] == "_search":
                self._send_json(store.search(parts[0], self._read_json()))
                return
            self._handle_write()

        def _handle_write(self) -> None:
            parts = self._path_parts()
            body = self._read_json()
            if len(parts) == 1:
                store.create_index(parts[0], body)
                self._send_json({"acknowledged": True, "index": parts[0]})
                return
            if len(parts) >= 3 and parts[1] == "_doc":
                doc_id = unquote("/".join(parts[2:]))
                store.index_document(parts[0], doc_id, body)
                self._send_json({"result": "created", "_index": parts[0], "_id": doc_id})
                return
            self.send_error(404, "Not found")

        def _path_parts(self) -> list[str]:
            return [part for part in urlparse(self.path).path.strip("/").split("/") if part]

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0") or 0)
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length) or b"{}")

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("x-opensearch-product", "OpenSearch")
            self.end_headers()

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.send_header("x-opensearch-product", "OpenSearch")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[maya-dev-opensearch] {self.address_string()} - {format % args}")

    return DevOpenSearchHandler


def create_server(host: str, port: int, store: DevOpenSearchStore | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_for(store or DevOpenSearchStore()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a tiny local OpenSearch-compatible service for Maya.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=9200, type=int)
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    print(f"Maya dev OpenSearch running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
