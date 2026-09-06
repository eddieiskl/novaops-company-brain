# NovaOps final project — submission

Fill this in and commit it to your repository as `SUBMISSION.md`. It is the first thing read,
and it is how every trace gets found.

---

## 1. Repository

| | |
| ------------------- | ------------------------------------------------ |
| **Repository URL**  | `https://github.com/eddieiskl/novaops-company-brain` |
| **Access**          | public |
| **Commit reviewed** | `d4d798adac9ad4ab6920a72037ab8d27a93fc0ff` |

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
| `M-I-01` | — | 0f3cbb817f2b0d80a8c87ed191c42cca |
| `M-I-02` | — | f614d5f0d2157cc31e3baa37193f2a71 |
| `M-I-03` | — | 79e57ceb4c41ac1a9a8b01817289e78f |
| `M-S-01` | 1 | 46ad616837eff75dea7e5afb008985c5 |
| `M-S-01` | 2 | c13956790b244d4b87fa971bd07572e7 |
| `M-S-01` | 3 | a923b2d101d87847285f135809ef7d37 |
| `M-S-01` | 4 | 366ebef5ef5f58bc09505bbc006e4daa |
| `M-S-01` | 5 | d5f2c33501f88b8d684dee46d4038620 |
| `M-S-01` | 6 | 7fdc16223353554a46934bba24eb3986 |
| `M-S-01` | 7 | 7d2e226328e05122f094b766fcb377d5 |
| `M-S-01` | 8 | 849954ce58c94d8d88206dc3e9b9e9ca |
| `M-S-01` | 9 | 6a4b4b22286cf3aabbe63e046fed7066 |
| `M-S-01` | 10 | 61904562d9090367ed951fdd4d65c0c3 |
| `M-S-01` | 11 | f6ac109b3866b6826f97118a2585d5e4 |
| `M-S-01` | 12 | dd320f268069ae7847036ff7d787b135 |
| `M-S-02` | 1 | 3715e2f3c9d6b7cbcdb9a912fa8a6064 |
| `M-S-02` | 2 | ca80c47bc60e35d7b15b6e93bc7890d9 |
| `M-S-02` | 3 | a242aca3e2ba2c3fdd58c0f0deea0d62 |
| `M-S-02` | 4 | 05435c0208ba5c59c737f027dbb0b45e |
| `M-S-02` | 5 | 3f5888bf6daa1285d29bd500f35564b8 |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | c9a494fcbab2d01ce55881da2a52134f |
| `W-I-02` | — | 5647035bd19fcaf26259a6a04b8adf29 |
| `W-I-03` | — | 7520da842a471f5ae1c81fd5b103e92f |
| `W-S-01` | 1 | 5568ed49e699bb237d33b3df16ffb88b |
| `W-S-01` | 2 | cabb33f20074ba55f6c2a1428d8e6176 |
| `W-S-01` | 3 | 654fddda19e13d23715c28c441271eb0 |
| `W-S-01` | 4 | 95ea62075e7b19d9a6d885c639f100dd |

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
