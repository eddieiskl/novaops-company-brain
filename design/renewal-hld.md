---
prd: output/novaops-renewal-prd-v1-3-clean/document.md
template: output/genai-application-hld-template-v2-1/document.md
status: local-implementation-baseline
date: 2026-09-23
---

**NovaOps Renewal HLD**

# 0. Document Control & Revision History

Version 1.0, 2026-09-23. Independent coursework design by Codex under the user’s request to complete the work. Engineering choices below are delegated implementation decisions, not individually approved Product rulings. The original PRD remains authoritative.

| **Version** | **Date** | **Author** | **Description of Changes** |
|---|---|---|---|
| 1.0 | 2026-09-23 | Codex / delegated engineering | Independent local design and acceptance baseline |

# 1. Executive Summary & Business Context

The service identifies renewal risk before employees report an access problem. It retains evidence, recommendations, decisions and supplier terms so a reviewer can tell what is proposed, approved, confirmed and effective. The local release corrects premature Webex activation and missing approval scope.

## 1.1 Objective & Scope

Scope: portfolio review and recommendations, the Webex reference approval/clearance and supplier round trip, durable future agreement, dated application, mock outbox and recovery tests. No employee access grant, autonomous spending, real supplier email or cloud deployment is part of the local acceptance run. Other portfolio cases stay visible for owner review.

## 1.2 Non-Functional Requirements (summary)

NFR-01 requires daily assessment and escalation within one working day; NFR-02 targets 95% processing within 15 minutes; NFR-03 targets 99.5% availability and recovery within 15 minutes. These are deployment objectives, not results inferred from unit tests. NFR-04–06 drive the gates, idempotency and confidentiality tests.

| NFR | Target | Notes |
|---|---|---|
| Timeliness | Daily; urgent within one working day | NFR-01 deployment target |
| Processing | 95% within 15 minutes | NFR-02 excludes human wait |
| Continuity | 99.5%; recovery within 15 minutes | NFR-03 production measurement pending |
| Authority/reliability | No premature or duplicate business effect | NFR-04/05 acceptance tests |
| Confidentiality | Traceable changes; minimal employee data | NFR-06 |

# 2. I/O Contract & Success Criteria

F-01 covers the schedule; F-02 covers scoped decisions; F-03 covers the supplier reply; F-04 covers effective-date activation. Each has durable outputs, with facts and recommendations stored separately from authority.

## 2.1 Input → Output Flows

A schedule takes an explicit as_of business date. It assesses records and activates only due persisted agreements. A provider reply can record a future agreement but cannot call activation itself.

| **Flow ID** | **Flow name** | **Input(s)** | **Input type / validation** | **Output(s)** | **Output shape / acceptance** |
|---|---|---|---|---|---|
| F-01 | Portfolio scan | as_of, current records | ISO date, SQL records | reviews, recommendations | FR-01–04; AC-01–03 |
| F-02 | Internal decision | event identity, actor, scope, clearance | assigned identity and typed scope | durable decision, request or pending reason | FR-05–07; AC-04–05 |
| F-03 | Supplier confirmation | email and Message-ID | schema, source, approved scope | future agreement or review case | FR-08–09; AC-06/08 |
| F-04 | Activation | as_of, future agreement | effective date and stored authority | effective update, notification intent | FR-10–13; AC-07/09–11 |

## 2.2 Flow Field Detail (optional)

Internal events carry event ID, run ID, contract ID, assigned actor, decision type, timestamp and approved scope where applicable. Scope contains action, seats, annual price ceiling and exact term. Finance clearance identifies AP002. The local event interface is trusted fixture/CLI input; production ingress needs authenticated identity binding.

| **Flow ID** | **Direction** | **Field / path** | **Type / Shape** | **Required?** | **Validation / Acceptance / Grounding** |
|---|---|---|---|---|---|
| F-02 | In | approved_scope | action; seats; annual ceiling; dates | Yes for approval | Reject missing or invalid scope |
| F-03 | Out | agreement | confirmation and complete commercial terms | Yes to activate | Exact seats/term; price within ceiling |

## 2.3 Definition of Done

AC-01 through AC-11 are the acceptance contract. July 3 confirmation leaves 40 seats and zero capacity notifications; July 21 creates one update and one notification per affected recipient. Replaying every input leaves the same business effects, with active usage still 42.

# 3. Architecture & Component Map

D1: deterministic schedule/event workflow with a bounded extraction call. D2: relational persistence and source-linked policy evidence. D3: one local transaction for each event and activation. Existing capstone extraction, database and instrumentation are reused.

## 3.1 Core Components

The scheduler calls the domain workflow. The workflow owns authority and transitions, the store owns durable records, adapters enqueue mock communication, and the extraction boundary returns schema-validated proposals. New capability required: future agreement, scope, clearance and delivery-state persistence.

| **Component** | **Responsibility** | **Example tech (optional)** |
|---|---|---|
| Schedule/event workflow | Authority and lifecycle | Existing Python worker |
| Store | Atomic durable state and idempotency | SQLite |
| Extractor | Untrusted reply to validated proposal | Existing model client + JSON schema |
| Outbox adapters | Communication intent and delivery state | Local mocks; injected transport |

# 4. Data Flow & Lifecycle

A recommendation is not a decision; a decision is not supplier confirmation; confirmation is not activation. These distinctions are represented by separate persisted facts and lifecycle states.

## 4.1 Trigger & Execution Mode

Use a scheduled worker and explicit event commands. The worker uses today’s date unless NOVAOPS_AS_OF is intentionally configured for replay. No chat session is required. A local single worker is sufficient for the acceptance dataset.

## 4.2 Primary Sequence (happy path)

Scan July 1 → recommend expansion → await scoped IT approval and Finance/security clearance → enqueue approved supplier request → validate July 3 reply → record future agreement → schedule July 21 → atomically apply and enqueue employee notification.

## 4.3 Tool / Model Execution Loop (if applicable)

One forced structured-extraction call interprets an untrusted supplier email. There is no agentic tool loop. Recommendation heuristics are explainable deterministic review prompts in the local release; a model may improve phrasing later without receiving write authority.

## 4.4 Lifecycle Events & Durable Execution

Internal events are validated and deduplicated by identity plus payload hash. Changed payload under the same identity is an error. Provider deduplication uses run and Message-ID. States include awaiting_internal_approval, awaiting_provider_reply, awaiting_effective_date, provider_review, stopped and completed. New capability required: approval/clearance event receipts commit with their transition and outbox entries.

# 5. Deployment & Capacity Model

D4: retain the existing local Python runtime and SQLite durability. The prior cloud/container patterns remain reusable but this change needs no new deployment or spending.

## 5.1 Runtime Topology

One scheduled process and trusted local event entrypoint share the SQLite database. The database file must live on persistent storage. External transports remain disabled unless explicitly integrated and authorized.

## 5.2 Scaling & Backpressure

Serialize write transactions. A database contention error is retryable before an effect commits. Keep uncertain outbound delivery visible; do not automatically resend it. Multi-worker scale requires deployment-specific locking, ingress authentication and delivery reconciliation before release.

## 5.3 Compute & Capacity Assumptions

The supplied portfolio is small enough for a bounded relational scan. No throughput capacity is asserted from the fixture count. Measure queue delay, transaction wait and processing duration before selecting production capacity.

# 6. Autonomy & Control Model

D1 and D5 keep authority deterministic and narrow. Human decision roles are checked independently of model output. New capability required: explicit security reviewer configuration; absent ownership blocks progress.

## 6.1 Control style

Select a fixed workflow with a bounded model extraction step. A fully autonomous renewal agent adds nondeterminism without removing the need for scoped authority, dated activation or durable evidence.

| **Style** | **When to use** | **Chosen?** |
|---|---|---|
| Deterministic workflow | Dates, authority, writes | Yes: D1 |
| Bounded extraction | Unstructured supplier text | Yes: schema and scope gate |
| Autonomous agent loop | Open-ended actions | No: not justified by PRD |

## 6.2 Budgets, stop conditions & HITL

Internal rejection stops the run. Missing scope or wrong actor is rejected without committing an event receipt. Missing clearance stays pending. Conditional, rejected, ambiguous, incomplete or mismatched supplier replies require review. A changed decision after a request is emitted requires an amendment path; it cannot overwrite the active request.

# 7. Tools & Integrations

All communication in the acceptance run uses local mocks and a durable outbox. The dispatcher is transport-injected; the local test transport does not contact anyone.

| **Tool** | **Purpose** | **Auth / scope** | **Sandbox / limits** | **Timeout / retry** | **On failure** |
|---|---|---|---|---|---|
| SQL context | Exact facts | Trusted worker; local dataset | Read for scan; guarded writes | Transaction failure surfaces | Retry after recovery |
| Model extractor | Supplier interpretation | Configured model client | No write tool | One extraction invocation | Pending/error or review |
| Notification/provider mocks | Durable outbox intent | Assigned recipient | No external send | No external retry | Queued or uncertain |

## 7.1 Tool safety principles

Model output is untrusted. Deterministic scope checks precede recording an agreement. Activation requires that exact recorded agreement and its effective date. The worker must not modify employee access records.

# 8. Data Sources & Retrieval Strategy

D2 selects SQL for exact structured facts and direct source-linked policy inspection. A vector index is unnecessary for the small fixed policy set and cannot substitute for scoped authority.

## 8.1 Retrieval pattern selection

Use joins for contract, subscription, demand and approval context. Keep the ownership-cleanup memo conflict visible for Figma and SupportDesk; do not grant the database or memo silent precedence over the approved PRD.

| **Pattern** | **When to use** | **Chosen?** | **Notes / scope** |
|---|---|---|---|
| SQL | Structured facts | Yes | Exact IDs and joins |
| Direct documents | Policy and owner conflict evidence | Yes | Preserve source disagreement |
| Vector RAG | Large narrative corpus | No | Unnecessary for local scope |

## 8.2 Data sources catalog

The schema and seed provide the concrete records. Policies and contract documents provide business interpretation. The newer Q3 memo concerns incremental spend; independent AP002 and security holds remain mandatory for Webex.

| **Source** | **Type** | **Access pattern** | **Freshness / ownership** | **ACL / tenancy** |
|---|---|---|---|---|
| Database schema/seed | Relational | Joins | Snapshot; record owners | Trusted local service |
| Policies/contracts/memos | Documents | Source-linked review | Dated policy evidence | Reviewer context |
| Supplier email | Untrusted text | Forced structured extraction | Message timestamp | Commercial reviewer only |

# 9. State, Memory & Retention

D3 retains runs, per-date portfolio reviews, scoped decisions, clearance records, event payload hashes, provider extraction, future agreements, effective update journal, outbox and notification records. Conversation memory is unnecessary. Keep all coursework evidence; production retention and deletion schedules need owner policy. No fabricated retention period is introduced.

| **State type** | **Contents** | **Store** | **TTL / retention** | **Access control** |
|---|---|---|---|---|
| Run/recommendation | Facts, rationale, next party | SQLite | Retain coursework evidence | Reviewer/worker |
| Authority | Scoped decision and clearances | SQLite | Production policy pending | Assigned actors |
| Agreement/update | Future and effective records | SQLite | Production policy pending | Guarded writer |
| Events/outbox | Payload identity, messages, status | SQLite | Production policy pending | Worker; no employee pricing |

# 10. Model Strategy & Cost / Latency Controls

Reuse the existing configured model client for live extraction; deterministic fixture extraction supports offline checks. Every model response is a proposal subjected to schema and business validation.

## 10.1 Model routing

Use one structured-output-capable model through the existing client. There is no need to choose a new provider for this lesson. On failure, retain the pending case and surface an error; never synthesize approval.

| **Task** | **Model class** | **Why** | **Fallback** |
|---|---|---|---|
| Reply extraction | Existing structured-output client | Reuses tested boundary | Fail closed; manual review |
| Offline validation | Deterministic fixture model | Repeatable orchestration tests | No production-quality claim |

## 10.2 Quality vs latency vs cost

Prefer short targeted context over the entire portfolio. The quality gate is accurate supported fields and correct lifecycle behavior. Production model latency and cost remain measurements to collect, not guessed numbers.

## 10.3 Context window management

Pass one supplier message and the extraction schema. Do not truncate critical commercial clauses silently; oversized input should be routed for review when a deployment input limit is configured.

## 10.4 Cost optimization

Deduplicate provider messages before invoking extraction. Keep retries bounded by the existing client; do not layer an unbounded agent retry loop around it. Cache durable event results, not authorization decisions across unrelated runs.

# 11. Availability, Resiliency & Failure Recovery

D3 makes event and activation transactions atomic. D6 distinguishes the local business transaction from network delivery: delivered requires an explicit receipt; sending after restart becomes uncertain. No automatic retry of uncertain messages.

| **Failure mode** | **Detection** | **System response** | **User-visible outcome** |
|---|---|---|---|
| Crash during event | Rollback on reopen | Replay event | No partial approval/request |
| Crash during activation | Atomic transaction | Replay schedule | No lost notification intent |
| Delivery timeout | No confirmed receipt | Mark uncertain | Owner reconciliation required |
| Missing reviewer | Authority gate | Keep pending | Configuration needed |

# 12. Security, Guardrails & Trust

The trust boundary separates source content, model proposals, trusted event inputs and persisted authority. Local fixtures are not proof of real identity. Production ingress must authenticate and bind actor identity before passing an event to this domain API.

## 12.1 Input & output policy

Reject malformed scopes, unknown decisions, contract mismatch, wrong actor, changed event payload and unsupported supplier terms. Ambiguous email content cannot become a commercial write.

## 12.2 Data privacy & egress

The employee notification contains neither pricing nor an access-grant claim. Internal commercial evidence stays in reviewer records and model input required for extraction. No real third-party message delivery is part of the local tests.

## 12.3 Identity, Authorization & Tool Execution

IT Manager identity comes from the contract owner department. Finance AP002 identifies its recorded approver. Security reviewer must be explicitly configured. Production authenticated ingress and secret management are deployment prerequisites.

| **Tool / Flow** | **Caller Context** | **Execution Identity** | **Permission Scope** | **Enforcement Point** |
|---|---|---|---|---|
| Approval | Assigned IT actor | Trusted event ingress | Contract and scope | Domain gate |
| Finance clearance | AP002 approver | Trusted event ingress | AP002/run | Domain gate |
| Security clearance | Configured reviewer | Trusted event ingress | Run | Fail closed if unset |
| Activation | Scheduled worker | Local service identity | Recorded agreement only | Date + transaction gate |

# 13. Observability & Evaluation

Retain evidence that distinguishes recommendation, scoped approval, clearance, confirmation, activation and communication. Existing observations wrap execution; the homework evaluator adds actual run traces and deterministic scores.

## 13.1 Tracing & telemetry

Trace schedule, internal decisions, extraction/validation, agreement handling and activation. Record run ID, event identity, state and business outcome. Avoid putting credential values into traces. Local evidence and hosted trace IDs are labeled separately.

## 13.2 Acceptance metrics (production)

Production targets are copied from NFR-01–06. Passing the offline AC suite proves tested behavior; it does not prove month-long availability or real delivery latency.

| **Metric** | **Target** | **How measured** |
|---|---|---|
| Daily assessment | NFR-01 | Scheduler/run journal |
| Processing latency | 95% within 15 minutes | Production trace durations; not measured here |
| Availability | 99.5% monthly | Production monitoring; not measured here |
| Unauthorized/premature updates | Zero in acceptance | AC tests |
| Duplicate business effects | Zero on replay | Unique records + restart tests |

## 13.3 Workflow / Behavioral Invariants

AC-01: calculate urgency from contract notice dates. AC-02: retain source-linked context. AC-03: produce an explicit recommendation with uncertainty. AC-04: require scoped authority and all clearances. AC-05: one accurate scoped supplier request. AC-06: future confirmation leaves capacity 40. AC-07: activate once on July 21 and keep active usage 42. AC-08: nonfinal or mismatched replies make no update and name the responsible next party. AC-09: crash/replay produces no duplicate effect and uncertain delivery stays uncertain. AC-10: no price or access-grant claim in employee updates. AC-11: persisted evidence connects every effect to its approval and confirmation.

## 13.4 Evaluation approach

Run AC-named deterministic tests, restart/crash tests and the three Renewal evaluation inputs. Compare before-effective and after-effective state. Preserve failures and fix the contract, rather than making the evaluator accept premature activation.

# 14. Decision Log (Required)

The decision log records choices made under the user’s delegated implementation scope. None is presented as a separate Product approval. Unresolved business ownership remains explicit and fail-closed.

## 14.1 Design choices we are confident about

D1–D6 are the architecture baseline used by the build. Related section references appear in each decision row.

| **Decision** | **Rationale** | **Alternatives rejected** |
|---|---|---|
| D1 Fixed lifecycle + bounded extraction (§3–6,10) | Rules and authority remain reproducible | Free-running agent; fully manual processing |
| D2 SQL + source evidence (§8, Appendix A) | Exact facts and visible conflicts | All data through RAG; silent source precedence |
| D3 Transactional durable state (§4,9,11,13) | Recover events and atomic notification intent | In-memory state; separately committed stages |
| D4 Reuse local Python/SQLite (§5) | Matches existing capstone and local workload | New managed cloud topology for coursework |
| D5 Explicit scoped authority (§6,7,12) | No implied security or Finance clearance | Approval-only gate; hardcoded approved terms |
| D6 Outbox with uncertain delivery (§7,11) | Honest external delivery state | Exactly-once network claim; blind retry |

## 14.2 Trade-offs accepted

The local release prioritizes explicit evidence and reproducible recovery. It accepts single-writer limits and manual reconciliation rather than claiming distributed exactly-once delivery.

| **Trade-off** | **We gain** | **We give up** |
|---|---|---|
| Single-writer SQLite | Simple atomic recovery | Distributed write throughput |
| Visible uncertain delivery | No blind duplicate commitment | Automatic timeout retry |
| Explicit security configuration | Fail-closed authority | Zero-configuration production operation |

## 14.3 Known weaknesses & risks

Production blockers are distinct from local acceptance: authenticated ingress, configured security ownership, real sender reconciliation, SLO measurement and retention policy. Existing historical capstone states need review because the earlier runtime allowed premature activation; tests use isolated fresh databases.

| **Weakness / risk** | **Impact** | **Mitigation / follow-up** |
|---|---|---|
| No production security owner decision | Clearance cannot proceed by default | Configure authenticated authorized reviewer |
| Historical premature updates | Existing records may be invalid | Review legacy runs; never silently undo commercial history |
| Production ingress/delivery/SLO unverified | Local tests cannot prove live service guarantees | Separate deployment acceptance |

## 14.4 First architectural decision (narrative)

First decide who owns authority. An LLM recommendation cannot substitute for the scoped approval, both clearances and supplier agreement. That choice determines the lifecycle, state and tests before framework selection.

# Appendix A - RAG / Vector Retrieval (Optional)

Not selected for this release (D2). Exact SQL plus a small source-linked policy set meet the local use case. Reassess RAG only if corpus size or discovery requirements justify it.

## A.1 Ingestion & parsing

The lab converter keeps source hashes, images and conversion findings. No OCR is performed. Conversion does not turn document text into instructions for the runtime.

## A.2 Chunking & metadata (implementation)

No vector chunking is needed in the renewal runtime. Retain source paths and exact evidence references in the review artifacts.

## A.3 Embedding & retrieval

No embedding index or reranker is introduced. Authorization remains in code regardless of future retrieval design.

# Appendix B - Token Budgets (Optional Detail)

The existing client owns model configuration; one reply per extraction is the bounded work unit. Input/output budgets and monetary caps for a production deployment require measured settings. They are not invented here.

| **Workflow / task** | **Primary model** | **Max input window** | **Target output budget** |
|---|---|---|---|
| Extraction | Existing configured client | One supplier message; deployment limit pending | Schema fields only |
| Recommendation | Deterministic local logic | One contract context | Rationale and uncertainty; no commitment |

# Appendix C - Evaluation Rubrics & Caching (Optional)

Behavioral invariants are deterministic. A semantic judge may help assess recommendation quality later, but cannot overrule the authority or date gate.

## C.1 Offline eval / LLM-as-judge

Evaluate supported fields, recommendation rationale and citation precision separately from writes. The local fixture model tests orchestration and the live extraction run tests the configured model boundary.

## C.2 Caching (optimization)

Event receipts prevent repeated extraction and effects for the same message. Do not reuse an approval or supplier result across contracts or changed payloads.
