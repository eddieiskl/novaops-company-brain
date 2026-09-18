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

Managed OpenSearch Serverless can be selected by collection name. The runtime resolves
the current endpoint and signs data-plane requests with SigV4:

```bash
MAYA_RETRIEVER=opensearch \
MAYA_OPENSEARCH_COLLECTION=<collection-name> \
MAYA_OPENSEARCH_SERVICE=aoss \
python3 novaops-final-project/web/server.py
```

`OPENSEARCH_COLLECTION` and `OPENSEARCH_ENDPOINT` remain accepted as course-level
fallbacks. Optional `OPENSEARCH_AWS_ACCESS_KEY_ID` and
`OPENSEARCH_AWS_SECRET_ACCESS_KEY` variables support a separate OpenSearch account.

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

## Retrieved-Content Guard And Quarantine

`maya.retrieval_security.GuardedEvidenceRetriever` decorates either retriever without
changing its authorization contract. It checks an exact quarantine registry first,
then requires the chunk ID, source path, and SHA-256 to match an application-owned
`TrustedCorpusManifest`. An optional `BedrockRetrievalGuard` can inspect the remaining
content. Rejected audit rows keep only chunk ID, source, digest, decision, and reason;
rejected text does not enter the answer prompt.

`MAYA_RETRIEVAL_SECURITY=provenance` is the default. Use `semantic` to add the Bedrock
content classifier or `off` only to prove that other application boundaries remain
independent. This closes the lesson's plausible-false-fact gap: a fluent document does
not become trusted merely because it contains no obvious injection language.

Run the owned recovery experiment only against the synthetic capstone index:

```bash
python evals/run_lesson13_capstone_poison.py
```

The runner refuses to insert if a prior owned poison remains, journals ownership before
submission, quarantines exact identity, verifies deletion, invalidates in-process thread
evidence, and checks both affected and fresh conversations after cleanup.

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

Retrieval tools enforce caller authorization. Internal approval tools are reached through the authenticated approval adapter; they are not model-visible approval authority.

## Lesson 14 Cloud Deployment

The gateway-backed path under `deploy/lesson14/` was exercised on ECS with encrypted
EFS and then cleaned up. The API+MCP task and LiteLLM task use distinct roles; only
the gateway can invoke the approved model. Cloud verification passed all 16 checks,
including pending approval surviving task replacement and replay without a duplicate
access request. A real scheduled automatic stop and final resource cleanup passed.

See `docs/lesson14-cloud-evidence.md` and `deploy/lesson14/README.md` for the exact
source snapshot, evidence, commands and limitations. The earlier `deploy/aws/`
EC2/renewal path remains an alternative prepared deployment, not the topology
verified by this run. No new public submission commit was published.
