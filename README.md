# NovaOps Company Brain — Final Project

This repository is the capstone implementation of NovaOps' permission-sensitive
operational company brain. The current required-workflow foundation is executable:
one public `CompanyBrainAgent` entry point scopes turns into Maya HR/onboarding or
Webex IT operations, reads the supplied corpus and operational database, filters
manager-only material before ranking, and keeps writes behind a durable,
recorded-approval gate.

## Current implementation map

| Claim | Evidence in the repository |
| --- | --- |
| Canonical project world is local and self-contained | `novaops-enterprise-agent-dataset/` |
| One entry point scopes Maya and Webex turns | `company_brain/agent.py` |
| Typed trace and terminal-state contract | `company_brain/schemas.py` |
| Corpus front matter is preserved during chunking | `maya/retrieval.py` |
| `audience: manager` is filtered before scoring | `maya/retrieval.py`, `tests/test_canonical_foundation.py` |
| Manager access derives from reporting relationships, not user group | `maya/ops.py:is_manager` |
| Operational state survives process restart | `maya/ops.py`, `tests/test_write_gate.py` |
| Model/user wording cannot directly authorize writes | `webex/write_gate.py` |
| Existing `T001` and `AR001` are reused | `webex/workflow.py`, `tests/test_webex_baseline.py` |
| Missing employee-to-seat data is represented honestly | `maya/ops.py:inspect_software_seat_assignments` |
| Tool capabilities are exposed through an MCP server | `retrieval_mcp_server.py`, `company_brain/mcp_client.py` |
| Bedrock Nova 2 Lite is isolated behind one model boundary | `model_client.py`, `maya/ports.py` |
| Langfuse emits agent/classify/scope/tool/answer spans | `company_brain/observability.py` |
| S2 and S9 long-session checks are committed | `evals/run_maya_s2.py`, `evals/run_maya_s9.py` |

## Stack and boundaries

- Python for application and evaluation code.
- SQLite for the supplied operational world and durable approval state. The
  default local database is `.state/novaops.sqlite3`; set `NOVAOPS_DB_PATH` to
  isolate a run.
- In-memory lexical retrieval for deterministic development, with the existing
  OpenSearch adapter available for production-shaped retrieval.
- FastMCP for the tool-server boundary.
- Langfuse remains the required submission channel; the final evaluation runner
  and trace index are the next milestone.
- Bedrock Nova 2 Lite will be the live answer model. Deterministic answers remain
  available so permission, idempotency, and restart tests never depend on a model.

The dataset intentionally has no employee-to-Webex-seat relation. The tool
`inspect_software_seat_assignments` returns that limitation explicitly; role
entitlement is never treated as evidence that a person holds a seat.

## Verification

From the course root:

```bash
.venv/bin/python -m pytest novaops-final-project/tests -q
.venv/bin/python novaops-final-project/evals/run_maya_s2.py
.venv/bin/python novaops-final-project/evals/run_maya_s9.py
.venv/bin/python novaops-final-project/evals/run_webex_s8.py
.venv/bin/python novaops-final-project/evals/run_submission.py
```

The current baseline is 47 passing tests, including canonical-corpus ingestion,
retrieval-layer permission filtering, noisy write-boundary behavior, idempotent
record reuse, wrong-approver rejection, and approval survival across a database
reconnect.

For the live MCP boundary, run these in separate terminals from this directory:

```bash
../.venv/bin/python retrieval_mcp_server.py
NOVAOPS_TOOL_MODE=mcp ../.venv/bin/python scripts/smoke_mcp.py
```

The official measured run sends the synthetic evaluation messages and retrieved
NovaOps evidence to the configured AWS Bedrock and Langfuse projects. Run it only
after confirming those destinations are approved:

```bash
NOVAOPS_TOOL_MODE=mcp NOVAOPS_ANSWER_MODE=bedrock \
  ../.venv/bin/python evals/run_submission.py --trace --update-submission
```

## Remaining required work

- Fill the repository URL, reviewed commit, Langfuse project, and instructor
  membership fields in `SUBMISSION.md`.

## Earlier Lesson 10/11 prototype history

This is the Lesson 10 homework implementation for the first NovaOps flagship workflow:
Maya Cohen's onboarding evidence agent.

## What This Builds

The `maya/` package adapts the Lesson 10 context-engineering ideas into final-project
application code:

- typed caller, plan, evidence, checklist, and Webex handoff models;
- caller-safe evidence retrieval with hard access filtering before ranking;
- dynamic read-tool loadouts with no direct write tool;
- thread-scoped memory for start date, location, Q3 freeze, closed tangents, and
  Webex handoff idempotency;
- deterministic replay of all twelve `S2-onboarding-maya` turns;
- optional model-backed answer generation behind `MAYA_ANSWER_MODE=model`;
- optional Lesson 9 pending-approval handoff behind `MAYA_WEBEX_PORT=lesson9`.

The implementation runs without Langfuse, AWS, OpenSearch, or model calls. The
retriever is an in-memory OpenSearch-style adapter over the Lesson 10 NovaOps dataset:
it stores source/chunk metadata, applies the hard caller filter before scoring, retrieves
wide, and reranks narrow. The boundary is intentionally shaped so a real OpenSearch
adapter can replace it later.

Optional extensions are included in `docs/optional-extensions.md`: an injectable
OpenSearch adapter, a model-backed answer mode, a Lesson 9 approval-port adapter, a
dashboard/chat UI, a token comparison note, and a read-only retrieval MCP server.

OpenSearch is off by default. Use the chat UI retriever toggle or set
`MAYA_RETRIEVER=opensearch` with `MAYA_OPENSEARCH_URL` to turn it on.
For local demos without Docker or AWS, run `novaops-final-project/scripts/start_maya_with_dev_opensearch.sh`;
it starts a tiny OpenSearch-compatible dev service, seeds the Maya evidence index, and
then launches the dashboard with OpenSearch selectable.

## Lesson 10 Baseline

Live Stage 3 evidence captured before the final-project adaptation:

- command: `python 03-history-distillation/graph.py --session S2`
- input tokens: `62,864`
- schema tokens: `10,028`
- calls: `36`
- score: `0.90`
- runtime: `35.4s`

This project preserves the Stage 3 responsibilities but replaces the classroom demo
write with a typed Webex handoff.

## Reuse Map

- Lesson 7: hard filter before ranking, retrieve-wide/rerank-narrow retrieval shape.
- Lesson 8: read-only NovaOps operational tools over employee, onboarding, assets,
  tickets, and subscriptions.
- Lesson 9: Webex becomes a separate approval workflow boundary.
- Lesson 10: planning, dynamic loadout, thread memory, closed tangent handling, and
  bounded S2 replay.

## Run

From the course root:

```bash
python3 -m pytest novaops-final-project/tests
python3 novaops-final-project/evals/run_maya_s2.py
python3 novaops-final-project/evals/token_comparison.py
```

The replay prints a per-turn summary and exits non-zero if any deterministic check
fails.

For the chat UI:

```bash
python3 novaops-final-project/web/server.py
```

For the chat UI with a local OpenSearch-compatible dev backend:

```bash
novaops-final-project/scripts/start_maya_with_dev_opensearch.sh
```

For the read-only retrieval MCP server:

```bash
python3 novaops-final-project/retrieval_mcp_server.py
```

Optional live modes:

```bash
MAYA_ANSWER_MODE=model MAYA_ANSWER_MODEL=<model> OPENAI_API_KEY=<key> python3 novaops-final-project/web/server.py
MAYA_WEBEX_PORT=lesson9 python3 novaops-final-project/web/server.py
```

## Lesson 11 Webex Baseline

Lesson 11 adds a measurable Rachel Stein Webex access baseline under `webex/` and
`evals/`. It is separate from the Maya onboarding agent: Rachel's workflow reuses the
existing ticket `T001` and access request `AR001`, preserves pending approvals, and
never claims access was granted while Webex is over the 40-seat contract limit.

```bash
/Users/MacBook/Documents/AI\ Engineer\ Course/.venv/bin/python novaops-final-project/evals/webex_checks.py
/Users/MacBook/Documents/AI\ Engineer\ Course/.venv/bin/python novaops-final-project/evals/run_webex_baseline.py --json
```

See `evals/WEBEX_BASELINE.md` for the Langfuse trace and judge commands.
