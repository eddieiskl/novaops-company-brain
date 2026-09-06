# NovaOps final project — submission

Fill this in and commit it to your repository as `SUBMISSION.md`. It is the first thing read,
and it is how every trace gets found.

---

## 1. Repository

| | |
| ------------------- | ------------------------------------------------ |
| **Repository URL**  | `https://github.com/eddieiskl/novaops-company-brain` |
| **Access**          | public |
| **Commit reviewed** | `0558d2f41e21e4844e4693f7f271d5cc0e4c9640` |

## 2. Langfuse

| | |
| ------------------ | --------------------------------------------- |
| **Host region**    | `cloud.langfuse.com` EU |
| **Project name**   | My Project |
| **Instructor role**| Member *(required — traces are read through the API)* |
| **Invitation accepted** | no — instructor invitation still required |

## 3. Scope completed

| Workflow | Built | Notes |
| --------------------------- | ------ | ----- |
| 1 — Maya · HR and onboarding | yes | S2 and S9 sessions, cited retrieval, read-only handoff |
| 2 — Webex · IT operations    | yes | durable approval gate, reuse of T001/AR001, honest seat limitation |
| 3 — Vendor · CRM extraction  | yes | one forced-tool call, schema validation, 0/1/2 missing fields |
| 4 — Renewal · contract renewal | yes | scheduled durable state, restart/replay safety, strict provider write gate |

| Optional stage | Done | Evidence |
| ------------------------------- | -------- | -------- |
| Lesson 12 — loop engineering     | yes | bounded binding-score improvement loop in `evals/IMPROVEMENT_REPORT.md` |
| Lesson 13 — attack and guardrail extension | yes | focused suite in `evals/run_guardrail_attacks.py` |
| Lesson 14 — packaging and deploy | partial | three non-root images and Compose verified locally; cloud resources not provisioned |

## 4. Durable-behavior evidence

Some required behavior cannot be seen in a single trace. Point at the commit, test, or trace
that proves each — one line, or "not attempted".

| Check | Evidence |
| ------------------------------------------------------------- | -------- |
| Replaying a request creates no second ticket or access request | `tests/test_company_brain_agent.py`, `tests/test_access_handoff_resume.py` |
| A pending approval survives the process being killed and restarted | `tests/test_access_handoff_resume.py::test_new_access_request_pauses_survives_restart_and_resumes_once` |
| The write gate releases only against a recorded approval | `webex/write_gate.py`, `tests/test_write_gate.py` |
| *Renewal: every event replayed twice leaves one update and one notification per recipient* | `tests/test_renewal_workflow.py::test_approved_renewal_survives_restarts_and_replays_exactly_once` |

## 5. Trace index

One row per item in `EVALUATION-INPUTS.yaml` — 27 required, 33 with both optional workflows.
**Fill in the trace id column only**; the ids and turn numbers are already correct. Leave a row
blank if you did not run it.


### Maya - HR and onboarding

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `M-I-01` | — | 0106a9be197435d567f3955464958467 |
| `M-I-02` | — | e26e0f847899471d448e53bf97a027b3 |
| `M-I-03` | — | 713dbdd2cdbf334a1be827abba24d7c2 |
| `M-S-01` | 1 | 087d454b61e657e6d279d7e76259c6b4 |
| `M-S-01` | 2 | 9e92c66ae95b3ec1dacdd1b544a3d21f |
| `M-S-01` | 3 | 053b3e030d2c705825b9d54d5f968b02 |
| `M-S-01` | 4 | 2da32e21de48f95f89f3bee5025a8304 |
| `M-S-01` | 5 | ccde8c7277e51fd8506f0be6105fa765 |
| `M-S-01` | 6 | db0a8cff4cf0875e0456f5de5a65ddf7 |
| `M-S-01` | 7 | 2e22ee6b0403b596f1ca70acdd220c05 |
| `M-S-01` | 8 | fda0974fdc2fd345f248b1bcae193ca8 |
| `M-S-01` | 9 | c112a040ace5c6fc9e69d42cbd7e61e8 |
| `M-S-01` | 10 | 39de41cfc502f927d55de8b0df81a524 |
| `M-S-01` | 11 | 3700bbdb7b01f1ed61adbd2d574572d9 |
| `M-S-01` | 12 | cc8275acb6417e9387963229c4f83622 |
| `M-S-02` | 1 | ad5995e0145508415bc37181fc9cdcb9 |
| `M-S-02` | 2 | 5920740946ae525d31f9e15b14cd9696 |
| `M-S-02` | 3 | 69051ed31524b7fa7f9de76b793cdc5b |
| `M-S-02` | 4 | bc605529d937d9545fdba85464beb745 |
| `M-S-02` | 5 | 3d6227bbca9c73ac919dc409b701ed03 |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | a0610cbe6fe75955d4f7a9fa3eaa1d72 |
| `W-I-02` | — | 9abb094085976aa610be8bfec54a4a33 |
| `W-I-03` | — | 1b9f4bd623cc80cbe82af063fb9bfbb6 |
| `W-S-01` | 1 | 699482104ee5aa8e6df6f84d44243af1 |
| `W-S-01` | 2 | 9d26c8fcb0958ab60975d13dc5f022d1 |
| `W-S-01` | 3 | 3fba761b7f7e03ce0dc1f6dacf77518a |
| `W-S-01` | 4 | 36a92c65efd56df79537ed64f5d81380 |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | fb6083721ce732712c42387b136cf8e7 |
| `V-I-02` | — | 4957099a73f2a7c14be419f837fd020e |
| `V-I-03` | — | 4d7863d0fb1ee8c0c9767ef570a9c8ef |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | 46f6e23f0d9332c3e157107e0ba7167b |
| `R-I-02` | — | e7e12e96ed5f7dbc031890866c85d4cc |
| `R-I-03` | — | f13cb72dc5451fec99b7ba79310afdf2 |

---

## 6. Anything I should know

All four workflows are implemented. Vendor produces schema-validated extractions; Renewal persists
its schedule, approval, provider proposal, outbox, update, audit, and notification state and is
replay-safe across restarts. Lesson 12 and the focused Lesson 13 extension are documented. Lesson 14
packaging was built and exercised locally across the API, MCP, and worker images; no cloud resources
were provisioned without explicit cost authorization. Live evaluations use Bedrock Nova 2 Lite;
deterministic fallbacks remain available for repeatable local safety tests.
