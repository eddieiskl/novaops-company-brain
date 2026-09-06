# Optional Extensions

## OpenSearch Adapter

`maya.retrieval.OpenSearchEvidenceRetriever` is an injectable adapter for a configured
OpenSearch-compatible client. It indexes the same NovaOps evidence chunks used by the
offline retriever, builds the hard caller filter before search, retrieves a wider result
set, and returns a small reranked cited set to the Maya graph.

Local tests use a fake OpenSearch client so the query boundary is verified without
requiring AWS or a running cluster.

Set `MAYA_DATASET_ROOT=/path/to/novaops/data` to point either retriever at a different
NovaOps dataset root.

For the easiest local demo, use the bundled dev service:

```bash
novaops-final-project/scripts/start_maya_with_dev_opensearch.sh
```

That script starts `dev_opensearch_server.py`, waits for `/_cluster/health`, sets
`MAYA_OPENSEARCH_URL`, and launches the Maya dashboard. The dashboard still starts in
memory mode by default, but the Runtime selector can switch to OpenSearch immediately.

The app defaults to OpenSearch off:

```bash
MAYA_RETRIEVER=memory python3 novaops-final-project/web/server.py
```

To start with OpenSearch on, install `opensearch-py` and set:

```bash
MAYA_RETRIEVER=opensearch MAYA_OPENSEARCH_URL=http://127.0.0.1:9200 python3 novaops-final-project/web/server.py
```

When `MAYA_OPENSEARCH_URL` is set, Maya auto-indexes its bundled evidence on startup by
default. Set `MAYA_OPENSEARCH_AUTO_INDEX=0` to skip that step for an already-managed
index.

The chat UI also has a retriever toggle. If OpenSearch is not configured, the API
returns a clear error and leaves memory mode active.

## Chat UI

Run the chat surface from the course root:

```bash
python3 novaops-final-project/web/server.py
```

Open `http://127.0.0.1:4180`. The UI calls the same `MayaAgent.handle_turn_sync` path
used by the deterministic tests.

The first tab is a dashboard backed by `GET /api/dashboard`. It replays the S2 workflow
into a compact readiness snapshot: item counts, systems, equipment, policy
requirements, blockers, evidence sources, retriever mode, and the per-turn tool trace.

## Model-Backed Answer Mode

The default Maya path uses deterministic answer templates so the homework replay stays
stable without model credentials. For a live demo, enable model-backed final wording:

```bash
MAYA_ANSWER_MODE=model MAYA_ANSWER_MODEL=<model> OPENAI_API_KEY=<key> python3 novaops-final-project/web/server.py
```

Maya still builds the same plan, evidence, checklist, and handoff state before calling
the answer model. If model mode is misconfigured, runtime status reports the reason and
falls back to deterministic answers.

## Lesson 9 Webex Approval Port

The default Webex port is a deterministic fake with idempotent pending handoffs. To
connect Maya's typed handoff to the Lesson 9 pending-approval write boundary, run:

```bash
MAYA_WEBEX_PORT=lesson9 python3 novaops-final-project/web/server.py
```

This adapter calls Lesson 9's `create_access_request` database function and returns its
`pending_approval` request id. Maya still never exposes `create_access_request` as one
of its own tools; the write stays behind the typed Webex port.

## Token Comparison

Captured Lesson 10 Stage 3 S2 baseline:

- final-turn input tokens: `62,864`
- schema tokens: `10,028`
- score: `0.90`
- runtime: `35.4s`

The Maya final-project replay currently uses deterministic application logic for the
answering path, so the final-turn answering-model input token count is `0`. That is not
a production quality claim; it is a deliberate homework boundary so context-policy,
retrieval authorization, handoff idempotency, and replay behavior can be tested without
Langfuse, Bedrock, or OpenSearch.

Run:

```bash
python3 novaops-final-project/evals/token_comparison.py
```

## Read-Only Retrieval MCP

Run the evidence MCP server from the course root:

```bash
python3 novaops-final-project/retrieval_mcp_server.py
```

It exposes:

- `list_evidence_collections()`
- `retrieve_evidence(query, caller_employee_id, caller_user_group, subject_employee_id, intent, limit)`

The server never exposes write tools and enforces caller authorization before retrieval.
