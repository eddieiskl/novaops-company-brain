# NovaOps Company Brain

NovaOps Company Brain is a permission-sensitive operational system with four workflows: Maya for HR/onboarding, Webex for IT access operations, standalone Vendor CRM extraction, and an offline Renewal process. It combines cited document retrieval, SQLite-backed operational records, an MCP tool boundary, Bedrock Nova 2 Lite structured output and answers, durable approval gates, Langfuse evaluation traces, and containerized entry points.

The repository is self-contained. Its company records and documents are synthetic and live under `novaops-enterprise-agent-dataset/`.

## What is implemented

| Claim | Repository evidence |
| --- | --- |
| One entry point classifies and scopes Maya and Webex requests | `company_brain/agent.py` |
| Actual classify → scope → execute → tools → answer work is traced | `company_brain/instrumentation.py`, `company_brain/observability.py`, `company_brain/tools.py` |
| MCP carries caller identity, scope, and required evidence | `retrieval_mcp_server.py`, `company_brain/tools.py` |
| Manager-only sources are filtered before ranking | `maya/retrieval.py`, `tests/test_canonical_foundation.py` |
| Manager access derives from reporting relationships, not a claimed group | `maya/ops.py`, `tests/test_maya_permissions.py` |
| Operational state and pending approvals survive restart | `maya/ops.py`, `tests/test_access_handoff_resume.py` |
| Model text cannot directly authorize a write | `webex/write_gate.py`, `tests/test_write_gate.py` |
| Existing Webex ticket `T001` and request `AR001` are reused | `webex/workflow.py`, `tests/test_webex_baseline.py` |
| Missing employee-to-seat data is reported rather than inferred | `maya/ops.py`, `tests/test_company_brain_agent.py` |
| Binding golden facts, sources, permissions, and tool-use rules are scored | `evals/binding_checks.py`, `tests/test_submission_runner.py` |
| All 27 required measured turns have a trace index | `SUBMISSION.md`, `evals/run_submission.py` |
| Vendor extraction uses one forced-tool call and validates the supplied schema locally | `vendor/extractor.py`, `tests/test_vendor_extractor.py` |
| Renewal pauses, survives restart, and replays every event exactly once | `renewal/`, `tests/test_renewal_workflow.py` |
| Adversarial permission, approval, and provider proposals fail closed | `evals/run_guardrail_attacks.py`, `tests/test_guardrail_attacks.py` |
| A typed input guard runs before planning and can be tested independently of server authorization | `company_brain/security.py`, `evals/run_lesson13_offline.py`, `tests/test_input_guard.py` |
| Retrieved content can be semantically screened or quarantined by exact ID/source/SHA-256 before the answer model | `maya/retrieval_security.py`, `tests/test_retrieval_guard.py` |
| A project-specific poison reaches a real OpenSearch-backed Bedrock answer, then is contained, deleted, and cleared from thread memory | `evals/run_lesson13_capstone_poison.py`, `docs/lesson13-capstone-poison-incident.md` |
| API, MCP, and worker ship as separate non-root containers, with a cost-gated AWS/EFS deployment path | `Dockerfile.*`, `docker-compose*.yml`, `deploy/aws/`, `docs/deployment.md` |

## Architecture

`CompanyBrainAgent` owns routing and the shared conversational result contract. Maya and Webex remain focused internal scopes. Vendor is a synchronous document-in/record-out function; Renewal begins from a schedule and resumes on persisted inbound events. All conversational retrieval and operational calls cross a `ToolGateway`, which can run in-process for deterministic tests or against the FastMCP server. SQLite is the source of durable operational, approval, renewal, outbox, and idempotency state; the default database is `.state/novaops.sqlite3` and can be overridden with `NOVAOPS_DB_PATH`.

The dataset deliberately has no employee-to-Webex-seat relationship. Role entitlement is not proof of assignment, so `inspect_software_seat_assignments` returns that limitation explicitly.

## Install and verify

Python 3.11 or newer is required.

```bash
git clone https://github.com/eddieiskl/novaops-company-brain.git
cd novaops-company-brain
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest -q
```

Run the committed deterministic evaluations:

```bash
python evals/run_maya_s2.py
python evals/run_maya_s9.py
python evals/run_webex_s8.py
python evals/run_submission.py
python evals/run_submission.py --include-optional
python evals/run_guardrail_attacks.py
python evals/run_lesson13_offline.py
```

With the synthetic AWS/OpenSearch environment configured, the Lesson 13 live evidence
commands are:

```bash
python evals/run_lesson13_live.py
python evals/run_lesson13_capstone_poison.py
```

The submission runner maps every required measured input to binding expectations from `spec/GOLDEN-DATASETS.json` or an explicit Webex check. It exits non-zero when a required fact/source, permission rule, tool-use rule, or generic safety invariant fails.

## MCP and live model mode

Start the MCP server in one terminal:

```bash
source .venv/bin/activate
python retrieval_mcp_server.py
```

Smoke-test it from another:

```bash
source .venv/bin/activate
NOVAOPS_TOOL_MODE=mcp python scripts/smoke_mcp.py
```

For a traced Bedrock run, create a local `.env` or export credentials for AWS and Langfuse, then run:

```bash
NOVAOPS_TOOL_MODE=mcp NOVAOPS_ANSWER_MODE=bedrock NOVAOPS_GUARD_MODE=bedrock \
  python evals/run_submission.py --include-optional --trace --update-submission
```

This sends synthetic evaluation prompts and retrieved synthetic NovaOps evidence to the configured AWS Bedrock and Langfuse projects. Never commit `.env`; it is ignored.

## Evaluation and observability

Each measured turn creates one Langfuse trace—27 for required scope and 33 with both optional workflows. Multi-turn trace inputs include prior conversation, declared evaluation criteria, and the evidence or verified operation state used by the answer. Large source documents stay in observation inputs rather than propagated metadata. The phase and tool observations wrap live execution, and tool observations record real arguments, results, completion state, and errors. Bedrock answer and structured-extraction calls appear as generation observations. Deterministic score comments explain every result rather than reporting an unexplained aggregate pass.

The bounded improvement record is in `evals/IMPROVEMENT_REPORT.md`. The final trace IDs and reviewed commit are recorded in `SUBMISSION.md`.

GitHub Actions runs pytest, the optional-inclusive 33-case promotion gate, the focused guardrail attacks, Compose validation, and a build of all three container images.

## Completion status

| Stage | Status |
| --- | --- |
| Required Maya workflow | Complete |
| Required Webex workflow | Complete |
| Lesson 11 observability and evaluation | Complete; instructor membership remains an external submission step |
| Lesson 12 eval-loop engineering | Complete for the required scope; before/after gate is documented |
| Vendor workflow | Complete; three schema-valid 0/1/2-gap extractions |
| Renewal workflow | Complete; three restart-safe, replay-safe outcomes |
| Lesson 13 security homework | Complete; 16-case live semantic guard, independent enforcement proof, project-specific OpenSearch poisoning/recovery evidence, and application-owned retrieval provenance |
| Lesson 14 packaging/deployment | ECS/LiteLLM/EFS verified: 108 tests, 22 local checks, 16 cloud checks, task-replacement persistence and automatic stop; cleanup verified. See `docs/lesson14-cloud-evidence.md`. |

## Security and data handling

- Secrets and runtime databases are ignored by Git.
- Regular employees never receive manager-only chunks.
- Direct write tools are absent from Maya’s model-visible loadouts.
- A recorded, assigned human approval is required before a gated write can be released.
- Retrieved chunks must match the application-owned ID/source/SHA-256 corpus manifest; semantic inspection and exact quarantine provide additional containment.
- Quarantined evidence is explicitly invalidated from in-process conversation memory after corpus cleanup.
- Answers distinguish observed facts, actions taken, recommendations, and blockers.

See `SUBMISSION.md` for the deliverable index and `spec/PROJECT-DESCRIPTION.md` for the supplied project brief.

The Lesson 13 boundary map, evidence limitations, offline commands, and live-resumption checklist are in [`docs/lesson13-security-homework.md`](docs/lesson13-security-homework.md). The isolated showcase includes a Security view with live blocked, allowed, and human-review probes that report the tool path and durable-state delta.

## Containers

```bash
IMAGE_TAG="$(git rev-parse HEAD)" docker compose build
IMAGE_TAG="$(git rev-parse HEAD)" docker compose up -d
curl http://127.0.0.1:18080/health/live
curl http://127.0.0.1:18080/health/ready
```

See `docs/deployment.md` for entry points, durability, credentials, cost, cleanup, and cloud-deployment boundaries. `docs/lesson14-cloud-evidence.md` is the reviewer-facing live evidence record.

The [Lesson 14 vendor extension](docs/lesson14-vendor-extension.md) adds bounded provider retries, one schema repair, and an SQS consumer sharing the HTTP extraction function. The project suite passes 118 tests; all three live vendor fixtures passed the expected 0/1/2 missing-field checks.
