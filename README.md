# NovaOps Company Brain

NovaOps Company Brain is a permission-sensitive operational agent with one public entry point and two required workflows: Maya for HR/onboarding questions and Webex for IT access operations. It combines cited document retrieval, SQLite-backed operational records, an MCP tool boundary, Bedrock Nova 2 Lite answers, durable approval gates, and Langfuse evaluation traces.

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

## Architecture

`CompanyBrainAgent` owns routing and the shared result contract. Maya and Webex remain focused internal workflows. All retrieval and operational calls cross a `ToolGateway`, which can run in-process for deterministic tests or against the FastMCP server. SQLite is the source of durable operational and approval state; the default database is `.state/novaops.sqlite3` and can be overridden with `NOVAOPS_DB_PATH`.

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
NOVAOPS_TOOL_MODE=mcp NOVAOPS_ANSWER_MODE=bedrock \
  python evals/run_submission.py --trace --update-submission
```

This sends synthetic evaluation prompts and retrieved synthetic NovaOps evidence to the configured AWS Bedrock and Langfuse projects. Never commit `.env`; it is ignored.

## Evaluation and observability

Each measured turn creates one Langfuse agent trace. The phase and tool observations wrap live execution, and tool observations record real arguments, results, completion state, and errors. Bedrock calls appear as generation observations. Deterministic score comments explain every binding result rather than reporting an unexplained aggregate pass.

The bounded improvement record is in `evals/IMPROVEMENT_REPORT.md`. The final trace IDs and reviewed commit are recorded in `SUBMISSION.md`.

## Completion status

| Stage | Status |
| --- | --- |
| Required Maya workflow | Complete |
| Required Webex workflow | Complete |
| Lesson 11 observability and evaluation | Complete; instructor membership remains an external submission step |
| Lesson 12 eval-loop engineering | Complete for the required scope; before/after gate is documented |
| Lesson 13 attack/guardrail extension | Not claimed as a separate optional stage; required permission and write-boundary controls are tested |
| Lesson 14 packaging/deployment | Not completed; no deployment claim is made |
| Vendor and Renewal workflows | Optional, not attempted |

## Security and data handling

- Secrets and runtime databases are ignored by Git.
- Regular employees never receive manager-only chunks.
- Direct write tools are absent from Maya’s model-visible loadouts.
- A recorded, assigned human approval is required before a gated write can be released.
- Answers distinguish observed facts, actions taken, recommendations, and blockers.

See `SUBMISSION.md` for the deliverable index and `spec/PROJECT-DESCRIPTION.md` for the supplied project brief.
