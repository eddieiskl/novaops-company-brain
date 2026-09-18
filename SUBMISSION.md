# NovaOps final project — submission

Fill this in and commit it to your repository as `SUBMISSION.md`. It is the first thing read,
and it is how every trace gets found.

---

## 1. Repository

| | |
| ------------------- | ------------------------------------------------ |
| **Repository URL**  | `https://github.com/eddieiskl/novaops-company-brain` |
| **Access**          | public |
| **Commit reviewed** | `6f7e97b2f69a0d99907444668e8b38e1f24b612d` |

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
| Lesson 14 — packaging and deploy | yes | ECS/LiteLLM/EFS: 16 cloud checks, durable approval restart/replay, automatic stop, and verified cleanup. See `docs/lesson14-cloud-evidence.md`. |

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
| `M-I-01` | — | 3885f2daaf15030fb961cb93b2c0728b |
| `M-I-02` | — | 397c36a524820a79889e082983732be2 |
| `M-I-03` | — | 824366b1c10ac96193637a01d9320564 |
| `M-S-01` | 1 | d0de64c758b06641e229bdcc11fc23ac |
| `M-S-01` | 2 | a7da772c7b7e154e5fcc24d2947d4edc |
| `M-S-01` | 3 | b74dd132f3bd378f5a8c692f9b4274c4 |
| `M-S-01` | 4 | 0339c6d424a292d2eaa48b18d17f3dfd |
| `M-S-01` | 5 | a07f0b7a885386366eab2b969389de22 |
| `M-S-01` | 6 | 441fcc266467734f45c605323bc21ff5 |
| `M-S-01` | 7 | 80ec5db85b5d1ac6b5b6c186850488a2 |
| `M-S-01` | 8 | b633a32e5a90e076c4a217ed3e6b4c00 |
| `M-S-01` | 9 | 353f75037dda1af14c0f8ecc78c55767 |
| `M-S-01` | 10 | 40676b57e849aff7fc1b6b1a7c07e38c |
| `M-S-01` | 11 | 616f04a5c8a1d3dbb4484af580259a85 |
| `M-S-01` | 12 | 206be68bbf04f3d24002284ebc8b7e41 |
| `M-S-02` | 1 | f558e2fd1918deddf1f5f9df4bc4b039 |
| `M-S-02` | 2 | 92fe878e22d343ac4eef4623069afb6f |
| `M-S-02` | 3 | 274385b0087bce482cc06d381a3387c5 |
| `M-S-02` | 4 | 61f16ece699ad6d3586c45c553639ce4 |
| `M-S-02` | 5 | 59e6b198f76a7d38a520a1703672ac8b |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | 42cbaa68b6794ff6c2cea461416192ec |
| `W-I-02` | — | 6dfbce2edb8ca1197d85e5589b3d69c9 |
| `W-I-03` | — | 09081868aa224b7da76e22563c536cae |
| `W-S-01` | 1 | 6427b56b2a062ff44ca87a0ccdde8471 |
| `W-S-01` | 2 | 83a60806de5de1684f204676721ec0a0 |
| `W-S-01` | 3 | c0a5976f7771674b16d0c3c1ef478e3d |
| `W-S-01` | 4 | 3807956e0d58b9854c925ce4a9809118 |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | a590c3a4ce2fdc0420a1a057eeab1863 |
| `V-I-02` | — | 697712230fa0463decd42462c14e64c3 |
| `V-I-03` | — | ec34e11c4cdb15fec8430355bf1798d0 |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | d22360d677d618149cb5e5a564ac0383 |
| `R-I-02` | — | 01feec7af347a2f8dfe6e09be3070880 |
| `R-I-03` | — | 505d2a8288e684ac7ab24d52e617a24c |

---

## 6. Anything I should know

All four workflows are implemented. Vendor produces schema-validated extractions; Renewal persists
its schedule, approval, provider proposal, outbox, update, audit, and notification state and is
replay-safe across restarts. Lesson 12 and the Lesson 13 extension are documented, including typed
input decisions, independent authorization, application-owned retrieval provenance, semantic
poison containment, exact cleanup, and memory invalidation. Lesson 14
gateway serving was verified locally and on ECS with encrypted EFS, separate model IAM,
durable approval restart/replay, and a working automatic stop. Cloud cleanup is verified.
The tested local source snapshot is recorded in `docs/lesson14-cloud-evidence.md`;
this run did not publish a new public submission commit. Live evaluations use Bedrock
Nova 2 Lite; deterministic fallbacks remain available for repeatable local safety tests.

## Lesson 14 vendor follow-up

Optional Task 2 is implemented and verified: bounded direct-provider retries, one schema repair, and a persistent-cache SQS consumer that publishes before acknowledging input. HTTP and queue delivery share the extraction function. All 118 project tests and the live 0/1/2 missing-field fixture checks pass. See [vendor evidence](docs/lesson14-vendor-extension.md).

The Lesson 14 follow-up is published for review in [PR #1](https://github.com/eddieiskl/novaops-company-brain/pull/1), branch `codex/lesson14-serving-vendor`. The historical reviewed submission SHA above remains unchanged until the new work is merged.

The separate [RDS-backed Lesson 14 course demo](docs/lesson14-rds-demo.md) also passed nine live checks, including cross-worker conversation persistence. All 32 resource-cleanup checks passed. The automatic-stop watcher was interrupted by connectivity loss, so its complete timing test is not claimed.
