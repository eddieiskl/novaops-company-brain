# NovaOps final project — submission

Fill this in and commit it to your repository as `SUBMISSION.md`. It is the first thing read,
and it is how every trace gets found.

---

## 1. Repository

| | |
| ------------------- | ------------------------------------------------ |
| **Repository URL**  | `https://github.com/eddieiskl/novaops-company-brain` |
| **Access**          | public |
| **Commit reviewed** | `4c26541134f27b9905f43a8306e4e71b4357a40f` |

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
| 3 — Vendor · CRM extraction  | no | optional workflow not attempted |
| 4 — Renewal · contract renewal | no | optional workflow not attempted |

| Optional stage | Done | Evidence |
| ------------------------------- | -------- | -------- |
| Lesson 12 — loop engineering     | yes | bounded binding-score improvement loop in `evals/IMPROVEMENT_REPORT.md` |
| Lesson 13 — attack and guardrail extension | no | not claimed separately; required permission/write controls are tested |
| Lesson 14 — packaging and deploy | no | dependency manifest and CI added; container/cloud stage not attempted |

## 4. Durable-behavior evidence

Some required behavior cannot be seen in a single trace. Point at the commit, test, or trace
that proves each — one line, or "not attempted".

| Check | Evidence |
| ------------------------------------------------------------- | -------- |
| Replaying a request creates no second ticket or access request | `tests/test_company_brain_agent.py`, `tests/test_access_handoff_resume.py` |
| A pending approval survives the process being killed and restarted | `tests/test_access_handoff_resume.py::test_new_access_request_pauses_survives_restart_and_resumes_once` |
| The write gate releases only against a recorded approval | `webex/write_gate.py`, `tests/test_write_gate.py` |
| *Renewal (optional): every event replayed twice leaves one update and one notification per recipient* | not attempted |

## 5. Trace index

One row per item in `EVALUATION-INPUTS.yaml` — 27 required, 33 with both optional workflows.
**Fill in the trace id column only**; the ids and turn numbers are already correct. Leave a row
blank if you did not run it.


### Maya - HR and onboarding

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `M-I-01` | — | 95041a3c4b8db240cbb0f48992a67c55 |
| `M-I-02` | — | 2b073f0a258ae4417ecb9dfdbf17b5b1 |
| `M-I-03` | — | c48312a2b323ae165023a531c4bb0bf0 |
| `M-S-01` | 1 | 265f8efc2e377678b4a4477b65a7f2dd |
| `M-S-01` | 2 | 0a41a869b3e640079f2fdf9211929e8a |
| `M-S-01` | 3 | fb5cafa61ed1db655d2f2e372e8be773 |
| `M-S-01` | 4 | 9b2ba295d34a0eab0efcb89bf6f9bb91 |
| `M-S-01` | 5 | 6dc9c0438d70447504326d289b0bdc16 |
| `M-S-01` | 6 | 7d3fe02605418323d7b4f09fab43b54f |
| `M-S-01` | 7 | cb36eddcb2ba70b3409aedef58929f05 |
| `M-S-01` | 8 | 7171faf954eaa23d323df331953952cc |
| `M-S-01` | 9 | b1e96b05d7b51fc8185f2450a1dac9cf |
| `M-S-01` | 10 | 4a8efb887e8a227c59241353ff81a2c8 |
| `M-S-01` | 11 | a66e6133bbc612bc252a5080c3a6005e |
| `M-S-01` | 12 | 844696a336d813b82ce29818fbf8defb |
| `M-S-02` | 1 | d1996720a3d6d6807d141ceb87ae209f |
| `M-S-02` | 2 | af68950416db8f608fc68dc42a1e4992 |
| `M-S-02` | 3 | ac084d531633125d830bf5f923ba51db |
| `M-S-02` | 4 | 3737f395791681a0b6ce31174ae83577 |
| `M-S-02` | 5 | 85fe2a5b215bc4730fa47724c6172bcf |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | 437c5933e3d4dc8985609d31342d1b46 |
| `W-I-02` | — | 4e3cd3bfb15df8ffd6ac6c29fc22fe94 |
| `W-I-03` | — | 1165d1f346bbe6e7e1d623d466231ef5 |
| `W-S-01` | 1 | 85bfc5abd62b8051b4d64a0339873cfc |
| `W-S-01` | 2 | f067402b15cfa6732e2e95afc1c27832 |
| `W-S-01` | 3 | 14fed43039a3b4b06cb9529fd25799ae |
| `W-S-01` | 4 | 7541c4834a0c307dbf97001802b61c29 |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | |
| `V-I-02` | — | |
| `V-I-03` | — | |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | |
| `R-I-02` | — | |
| `R-I-03` | — | |

---

## 6. Anything I should know

The required Maya and Webex scope is complete; Vendor, Renewal, and deployment were deliberately
left out so the required permission, approval, idempotency, and observability paths could be
finished and evidenced. Lesson 12's bounded improvement loop is documented and the project now
has a standalone dependency manifest plus CI, but no Lesson 14 deployment claim is made. The live
evaluation used Bedrock Nova 2 Lite through the MCP-backed core; deterministic answer fallbacks
remain available for repeatable local safety tests.
